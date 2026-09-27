/* global gradioApp, onUiLoaded, onUiUpdate */
(() => {
    "use strict";
    let currentPanel = null;
    let dispose = () => {};

    function boot() {
        const root = typeof gradioApp === "function" ? gradioApp() : document;
        const panel = root.querySelector("#hanaikada-panel");
        if (!panel || panel === currentPanel) return;
        dispose();
        currentPanel = panel;
        const status = panel.querySelector(".hanaikada-status");
        const frame = panel.querySelector("iframe");
        const base = new URL(window.location.pathname.replace(/\/?$/, "/") + "hanaikada/", window.location.origin);
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

        dispose = () => { stopped = true; clearTimeout(timer); };
        poll();
    }

    if (typeof onUiLoaded === "function") onUiLoaded(boot);
    if (typeof onUiUpdate === "function") onUiUpdate(boot);
    window.addEventListener("pagehide", () => dispose());
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) { currentPanel = null; boot(); }
    });
})();
