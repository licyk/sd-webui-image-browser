"""Optional browser fixture: real Gradio (3 or 4), a temporary WebUI folder, no Stable Diffusion imports.

Run with the host's Gradio and an installed Hanaikada release (its wheel carries the web UI).
The only login is smoke / smoke; this fixture binds exclusively to localhost.
"""

import argparse
import itertools
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gradio as gr

from sd_webui_image_browser import host as host_module
from sd_webui_image_browser.host import image_saved, mount_browser, on_ui_tabs
from tests.conftest import A1111_OPTIONS, make_host, save_png

HOOKS = """
window.gradioApp = () => document.querySelector('gradio-app')?.shadowRoot || document;
const callbacks = [];
window.onUiLoaded = window.onUiUpdate = (callback) => callbacks.push(callback);
function observe() {
    new MutationObserver(() => callbacks.forEach((callback) => callback())).observe(document.body, {subtree: true, childList: true});
    callbacks.forEach((callback) => callback());
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', observe);
else setTimeout(observe, 0);
"""


def inject(head: str, css: str) -> None:
    """What the WebUI's ui_gradio_extensions.reload_javascript does for extension scripts and styles."""
    original = gr.routes.templates.TemplateResponse

    def template_response(*args, **kwargs):
        response = original(*args, **kwargs)
        response.body = response.body.replace(b"</head>", f'{head}<meta name="referrer" content="no-referrer"/></head>'.encode())
        response.body = response.body.replace(b"</body>", f"<style>{css}</style></body>".encode())
        response.init_headers()
        return response

    gr.routes.templates.TemplateResponse = template_response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=17867)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    host_module.DATA_DIR = args.data_dir / "extension" / "data"
    webui = args.data_dir / "stable-diffusion-webui"
    outputs = webui / "outputs" / "txt2img-images"
    save_png(outputs / "00000-42.png")
    shared, paths = make_host(webui, A1111_OPTIONS)
    shared.state = SimpleNamespace(job_count=0, job="")
    os.chdir(webui)
    inject(
        "<script>" + HOOKS + (root / "javascript" / "hanaikada.js").read_text(encoding="utf-8") + "</script>", (root / "style.css").read_text(encoding="utf-8")
    )
    runtime = None
    counter = itertools.count(1)

    def simulate_save():
        # As modules.images.save_image does: write the file, then call on_image_saved.
        path = save_png(outputs / f"{next(counter):05d}-7.png", "a paper lantern\nSteps: 12, Sampler: Euler, CFG scale: 5, Seed: 7, Size: 8x8, Model: test")
        image_saved(runtime, SimpleNamespace(image=SimpleNamespace(already_saved_as=str(path)), filename=str(path)))
        return path.name

    browser_tab = on_ui_tabs()[0][0]
    with gr.Blocks(analytics_enabled=False) as demo:
        with gr.Tab("Hanaikada"):
            browser_tab.render()
        saved = gr.Textbox("", label="Saved image", elem_id="smoke-saved")
        gr.Button("Simulate save").click(simulate_save, outputs=saved)
    app, _, _ = demo.launch(server_name="127.0.0.1", server_port=args.port, auth=("smoke", "smoke"), prevent_thread_lock=True)
    runtime = mount_browser(demo, app, shared, paths)
    print(f"Gradio {gr.__version__} ready on http://127.0.0.1:{args.port}", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        demo.close()
        runtime.unload()
        assert runtime.task is None or runtime.task.done()
        print("Hanaikada lifespan stopped", flush=True)


if __name__ == "__main__":
    main()
