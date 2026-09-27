import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import vm from "node:vm";

const script = readFileSync(new URL("../javascript/hanaikada.js", import.meta.url), "utf8");
const settled = () => new Promise((resolve) => setImmediate(resolve));

async function panel(overrides = {}) {
    let boot;
    let sequence = 0;
    let httpStatus = 200;
    let failure = null;
    const timers = new Map();
    const state = {ui_available: true, default_root: "webui-1", combined_view: false, ...overrides};
    const status = {hidden: true, textContent: ""};
    const frame = {
        hidden: true,
        hasAttribute: (name) => Object.hasOwn(frame, name),
        removeAttribute: (name) => { delete frame[name]; },
    };
    const element = {
        querySelector(selector) {
            if (selector === ".hanaikada-status") return status;
            if (selector === "iframe") return frame;
            throw new Error(`Unexpected interface element requested: ${selector}`);
        },
    };
    const root = {querySelector: (selector) => (selector === "#hanaikada-panel" ? element : null)};
    vm.runInNewContext(script, {
        window: {location: {pathname: "/webui/", origin: "https://example.test"}, addEventListener() {}},
        document: root,
        onUiLoaded: (fn) => { boot = fn; },
        URL,
        URLSearchParams,
        AbortController,
        setTimeout: (fn, delay) => { const id = ++sequence; timers.set(id, {fn, delay}); return id; },
        clearTimeout: (id) => timers.delete(id),
        fetch: async (url, options) => {
            assert.equal(url.href, "https://example.test/webui/hanaikada/_host/status");
            assert.equal(options.credentials, "same-origin");
            if (failure) throw failure;
            return {status: httpStatus, ok: httpStatus === 200, json: async () => ({...state})};
        },
    });
    boot();
    await settled();
    return {
        frame, status, state,
        setResponse: (code, error = null) => { httpStatus = code; failure = error; },
        async poll() {
            const [id, timer] = [...timers].find(([, timer]) => timer.delay === 10000);
            timers.delete(id);
            await timer.fn();
        },
    };
}

test("connected panel shows the iframe without any status text", async () => {
    const ui = await panel();
    assert.equal(ui.frame.hidden, false);
    assert.equal(ui.frame.src, "https://example.test/webui/hanaikada/#/browse?root=webui-1");
    assert.equal(ui.status.hidden, true);
    assert.equal(ui.status.textContent, "");
});

test("the combined view opens Browse on All folders", async () => {
    const ui = await panel({combined_view: true});
    assert.equal(ui.frame.src, "https://example.test/webui/hanaikada/#/browse?root=*");
});

test("status polling keeps the folder chosen inside the browser", async () => {
    const ui = await panel();
    ui.frame.src = "https://example.test/webui/hanaikada/#/browse?root=webui-2&path=outputs";
    await ui.poll();
    assert.equal(ui.frame.src, "https://example.test/webui/hanaikada/#/browse?root=webui-2&path=outputs");
});

test("expired login hides the iframe and recovery clears the error", async () => {
    const ui = await panel();
    ui.setResponse(401);
    await ui.poll();
    assert.equal(ui.frame.hidden, true);
    assert.equal(ui.frame.hasAttribute("src"), false);
    assert.equal(ui.status.hidden, false);
    assert.match(ui.status.textContent, /登录已失效/);
    ui.setResponse(200);
    await ui.poll();
    assert.equal(ui.frame.hidden, false);
    assert.equal(ui.status.hidden, true);
    assert.equal(ui.frame.src, "https://example.test/webui/hanaikada/#/browse?root=webui-1");
});

test("missing assets and connection errors remain visible until recovery", async () => {
    const ui = await panel();
    ui.state.ui_available = false;
    await ui.poll();
    assert.equal(ui.frame.hidden, true);
    assert.equal(ui.status.hidden, false);
    assert.match(ui.status.textContent, /缺少前端资源/);
    ui.setResponse(200, new Error("offline"));
    await ui.poll();
    assert.match(ui.status.textContent, /无法连接.*offline/);
    ui.setResponse(200);
    ui.state.ui_available = true;
    await ui.poll();
    assert.equal(ui.frame.hidden, false);
    assert.equal(ui.status.hidden, true);
});
