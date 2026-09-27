import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";

const script = readFileSync(new URL("../javascript/hanaikada.js", import.meta.url), "utf8");
const settled = () => new Promise((resolve) => setImmediate(resolve));
const ORIGIN = "https://example.test";

/** The panel script in a sandbox, with send.py's hidden components as plain objects. */
function page({buttons = ["txt2img", "img2img", "img2img-image", "inpaint", "inpaint-image", "extras-image"], answer = {ok: true}, loads = true, stale = false} = {}) {
    let boot;
    let listener;
    const posted = [];
    const clicks = [];
    const timers = [];
    const frameWindow = {postMessage: (message, origin) => posted.push({message, origin})};
    const frame = {hidden: true, contentWindow: frameWindow, hasAttribute: () => true, removeAttribute() {}};
    const status = {hidden: true, textContent: ""};
    const panel = {querySelector: (selector) => (selector === ".hanaikada-status" ? status : selector === "iframe" ? frame : null)};
    const textarea = (value = "") => ({value, dispatchEvent() {}});
    const fields = {"hanaikada-send-request": textarea(), "hanaikada-send-status": textarea()};
    const window = {location: {pathname: "/", origin: ORIGIN}, addEventListener: (type, fn) => { if (type === "message") listener = fn; }};
    const elements = {"hanaikada-panel": panel};
    for (const [id, input] of Object.entries(fields)) elements[id] = {querySelector: () => input};
    elements["hanaikada-send-load"] = {
        click() {
            clicks.push("load");
            const {nonce} = JSON.parse(fields["hanaikada-send-request"].value);
            fields["hanaikada-send-status"].value = JSON.stringify(stale ? {ok: true} : {nonce, ...answer});
            if (loads) Promise.resolve().then(() => window.hanaikadaSendLoaded());
        },
    };
    for (const id of buttons) elements[`hanaikada-send-paste-${id}`] = {click: () => clicks.push(id)};
    const root = {querySelector: (selector) => elements[selector.replace(/^#/, "")] ?? null};
    vm.runInNewContext(script, {
        window, document: root, onUiLoaded: (fn) => { boot = fn; },
        updateInput: (input) => clicks.push(`input:${input.value}`),
        URL, URLSearchParams, AbortController, Event: class { constructor(type) { this.type = type; } },
        setTimeout: (fn, delay) => { timers.push({fn, delay}); return timers.length; },
        clearTimeout: () => {},
        fetch: async () => ({status: 200, ok: true, json: async () => ({ui_available: true, combined_view: true})}),
    });
    boot();
    const from = (data, source = frameWindow, origin = ORIGIN) => listener({data, source, origin});
    return {posted, clicks, timers, from, fields, frameWindow};
}

const item = {root_id: "webui-1", path: "outputs/txt2img-images/00000-42.png", name: "00000-42.png", kind: "image", url: `${ORIGIN}/hanaikada/f`, version: "1", size: 1};
const send = (target, infotext = "a cat\nSteps: 20") => ({ns: "hanaikada", v: 1, type: "send", id: `r-${target}`, target, payload: {item, infotext, platform: "sd-webui"}});

test("offers the targets whose paste buttons the page has", async () => {
    const {posted, from} = page({buttons: ["img2img-image", "extras-image"]});
    from({ns: "hanaikada", v: 1, type: "hello", app: "hanaikada"});
    assert.deepEqual(JSON.parse(JSON.stringify(posted)), [{
        message: {ns: "hanaikada", v: 1, type: "host", host: {name: "sd-webui", label: "Stable Diffusion WebUI", targets: [{id: "img2img"}, {id: "extras", needs: ["file"]}]}},
        origin: ORIGIN,
    }]);
});

test("ignores other windows, other origins and other protocols", async () => {
    const {posted, from} = page();
    from({ns: "hanaikada", v: 1, type: "hello"}, {postMessage() {}});
    from({ns: "hanaikada", v: 1, type: "hello"}, undefined, "https://evil.test");
    from({ns: "hanaikada", v: 2, type: "hello"});
    await settled();
    assert.equal(posted.length, 0);
});

test("loads the request, then pastes with the infotext and reports success", async () => {
    const {posted, clicks, from} = page();
    from(send("img2img"));
    await settled();
    await settled();
    const request = JSON.parse(clicks[0].slice("input:".length));
    assert.deepEqual(request, {nonce: "r-img2img", target: "img2img", root_id: "webui-1", path: item.path, infotext: "a cat\nSteps: 20"});
    assert.deepEqual(clicks.slice(1), ["load", "img2img"]);
    assert.deepEqual(JSON.parse(JSON.stringify(posted.at(-1).message)), {ns: "hanaikada", v: 1, type: "result", id: "r-img2img", ok: true});
});

test("without an infotext, or for Extras, the image goes alone", async () => {
    const {clicks, from} = page();
    from(send("inpaint", null));
    from(send("extras"));
    for (let i = 0; i < 6; i++) await settled();
    assert.deepEqual(clicks.filter((c) => !c.startsWith("input:")), ["load", "inpaint-image", "load", "extras-image"]);
});

test("passes on the WebUI's refusal, and gives up when it never answers", async () => {
    const refused = page({answer: {ok: false, message: "Not an image: x.txt"}});
    refused.from(send("img2img"));
    for (let i = 0; i < 3; i++) await settled();
    assert.deepEqual(JSON.parse(JSON.stringify(refused.posted.at(-1).message)), {ns: "hanaikada", v: 1, type: "result", id: "r-img2img", ok: false, message: "Not an image: x.txt"});
    assert.ok(!refused.clicks.includes("img2img"));

    const silent = page({loads: false});
    silent.from(send("img2img"));
    await settled();
    silent.timers.find((t) => t.delay === 30000).fn();
    for (let i = 0; i < 3; i++) await settled();
    assert.equal(silent.posted.at(-1).message.ok, false);
    assert.equal(silent.posted.at(-1).message.message, "The WebUI did not answer.");
});

test("never pastes from a status left over by an earlier request", async () => {
    const {posted, clicks, from} = page({stale: true});
    from(send("img2img"));
    for (let i = 0; i < 3; i++) await settled();
    assert.equal(posted.at(-1).message.ok, false);
    assert.ok(!clicks.includes("img2img"));
});

test("refuses targets the WebUI does not have", async () => {
    const {posted, from} = page();
    from(send("controlnet"));
    await settled();
    assert.equal(posted.at(-1).message.ok, false);
});
