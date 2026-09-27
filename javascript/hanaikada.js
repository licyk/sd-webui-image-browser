/* global gradioApp, onUiLoaded, onUiUpdate, updateInput */
(() => {
    "use strict";
    let currentPanel = null;
    let dispose = () => {};

    // -- Hanaikada's "Send to …": its host bridge (protocol v1) and send.py's hidden components --

    const NS = "hanaikada";
    const SEND = "hanaikada-send";
    // txt2img takes only the parameters; Extras only the image.
    const TARGETS = [{id: "txt2img", needs: ["infotext"]}, {id: "img2img"}, {id: "inpaint"}, {id: "extras", needs: ["file"]}];
    const appRoot = () => (typeof gradioApp === "function" ? gradioApp() : document);
    const element = (id) => appRoot().querySelector(`#${id}`);
    const field = (id) => element(id)?.querySelector("textarea, input");
    // Only targets whose paste buttons this page has (a WebUI without the paste API has none).
    const available = () => TARGETS.filter((t) => element(`${SEND}-paste-${t.id}`) || element(`${SEND}-paste-${t.id}-image`));
    const reply = (target, message) => target.postMessage({ns: NS, v: 1, ...message}, window.location.origin);

    // The WebUI's paste chain for inpaint calls this; Forge no longer defines it (A1111 does).
    if (typeof window.recalculate_prompts_inpaint !== "function") window.recalculate_prompts_inpaint = (...args) => args;

    let queue = Promise.resolve();
    let loaded = null;
    // send.py's load event calls this once its outputs are in place.
    window.hanaikadaSendLoaded = () => loaded?.();

    async function send({id, target, payload}, source) {
        const result = (ok, message) => reply(source, {type: "result", id, ok, ...(message ? {message} : {})});
        if (!TARGETS.some((t) => t.id === target)) return result(false, "The WebUI does not take this.");
        const item = payload?.item ?? {};
        const infotext = typeof payload?.infotext === "string" ? payload.infotext : "";
        const request = field(`${SEND}-request`);
        const load = element(`${SEND}-load`);
        if (!request || !load) return result(false, "The page has no send components; reload the WebUI.");
        // The nonce ties the status to this request: a load that failed inside Gradio leaves the
        // previous request's status in place, which must not be pasted from.
        request.value = JSON.stringify({nonce: id, target, root_id: item.root_id, path: item.path, infotext});
        if (typeof updateInput === "function") updateInput(request);
        else request.dispatchEvent(new Event("input", {bubbles: true}));
        const done = new Promise((resolve) => { loaded = () => resolve(true); });
        let timer;
        const expired = new Promise((resolve) => { timer = setTimeout(() => resolve(false), 30000); });
        load.click();
        const answered = await Promise.race([done, expired]);
        clearTimeout(timer);
        loaded = null;
        if (!answered) return result(false, "The WebUI did not answer.");
        let status = {};
        try { status = JSON.parse(field(`${SEND}-status`)?.value || "{}"); } catch { status = {}; }
        if (status.nonce !== id) return result(false, "The WebUI could not load the image; see its console.");
        if (!status.ok) return result(false, status.message || "The WebUI could not load the image.");
        // Without an infotext the image goes alone: an empty text would paste params.txt instead.
        const withText = infotext.trim() && target !== "extras";
        const paste = element(`${SEND}-paste-${target}${withText ? "" : "-image"}`);
        if (!paste) return result(false, "The WebUI does not take this.");
        // The WebUI fills the tab and switches to it, as its own "Send to" buttons do.
        paste.click();
        return result(true);
    }

    function boot() {
        const root = typeof gradioApp === "function" ? gradioApp() : document;
        const panel = root.querySelector("#hanaikada-panel");
        if (!panel || panel === currentPanel) return;
        dispose();
        currentPanel = panel;
        const status = panel.querySelector(".hanaikada-status");
        const frame = panel.querySelector("iframe");
        const base = new URL(window.location.pathname.replace(/\/?$/, "/") + "hanaikada/", window.location.origin);
        const onMessage = (event) => {
            // Only this panel's Hanaikada, on this page's own origin.
            if (event.source !== frame.contentWindow || event.origin !== window.location.origin) return;
            const data = event.data;
            if (!data || data.ns !== NS || data.v !== 1) return;
            if (data.type === "hello") reply(event.source, {type: "host", host: {name: "sd-webui", label: "Stable Diffusion WebUI", targets: available()}});
            else if (data.type === "send" && typeof data.id === "string") {
                const source = event.source;
                queue = queue.then(() => send(data, source)).catch(() => undefined);
            }
        };
        window.addEventListener("message", onMessage);
        let stopped = false;
        let timer;
        let inFlight = false;
        const message = (text = "") => {
            status.textContent = text;
            status.hidden = !text;
        };

        async function poll() {
            if (stopped || inFlight) return;
            inFlight = true;
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 20000);
            try {
                const response = await fetch(new URL("_host/status", base), {credentials: "same-origin", cache: "no-store", signal: controller.signal});
                if (stopped) return;
                if (response.status === 401) {
                    frame.hidden = true;
                    frame.removeAttribute("src");
                    message("WebUI 登录已失效，请刷新整个页面并重新登录。");
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const latest = await response.json();
                if (stopped) return;
                if (!latest.ui_available) {
                    frame.hidden = true;
                    message("Hanaikada 缺少前端资源，请安装包含 webui/dist 的发行包；源码安装需先构建前端。");
                    return;
                }
                if (!frame.hasAttribute("src")) {
                    const initial = new URL(base);
                    // "*" is Hanaikada's "All folders" entry: every output folder side by side.
                    const initialRoot = latest.combined_view ? "*" : latest.default_root;
                    if (initialRoot) {
                        initial.hash = `/browse?${new URLSearchParams({root: initialRoot})}`;
                    }
                    frame.src = initial.href;
                }
                frame.hidden = false;
                message();
            } catch (error) {
                if (!stopped) message(`无法连接 Hanaikada（${error.message}），正在重试；启动错误请查看 WebUI 控制台。`);
            } finally {
                clearTimeout(timeout);
                inFlight = false;
                if (!stopped) timer = setTimeout(poll, 10000);
            }
        }

        dispose = () => { stopped = true; clearTimeout(timer); window.removeEventListener("message", onMessage); };
        poll();
    }

    if (typeof onUiLoaded === "function") onUiLoaded(boot);
    if (typeof onUiUpdate === "function") onUiUpdate(boot);
    window.addEventListener("pagehide", () => dispose());
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) { currentPanel = null; boot(); }
    });
})();
