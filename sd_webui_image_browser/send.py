"""Hanaikada's "Send to txt2img / img2img / inpaint / extras", through the WebUI's own paste mechanism.

The Hanaikada frame asks the page (``javascript/hanaikada.js``) over its host bridge; the page puts
the request into hidden components built here and clicks one of the paste buttons registered with
``register_paste_params_button``. The WebUI then does what its own "Send to" buttons do: parse the
infotext into every field, set the image and its size, and switch tabs.

Values travel through Gradio components, so each browser session has its own; nothing is shared
between users. The file is resolved by Hanaikada, inside its roots, never from a path the page
names outright.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

TARGETS = ("txt2img", "img2img", "inpaint", "extras")
ELEMENT = "hanaikada-send"


def paste_module():
    """The WebUI's paste API: ``modules.infotext_utils`` since A1111 1.8, ``generation_parameters_copypaste`` before."""
    try:
        from modules import infotext_utils as module
    except ImportError:
        from modules import generation_parameters_copypaste as module
    return module


def js_keyword(gradio_version: str) -> str:
    """Gradio 3 names an event's front-end function ``_js``, Gradio 4 ``js``."""
    return "js" if int(gradio_version.split(".", 1)[0]) >= 4 else "_js"


def load(raw: str, services_getter: Callable[[], Any]) -> tuple[Any, str, str]:
    """``(image, infotext, status)`` for a request ``{nonce, target, root_id, path, infotext}``.

    ``status`` is JSON, ``{"nonce", "ok": true}`` or ``{"nonce", "ok": false, "message"}``, and the
    page pastes only when the nonce is its own: an event that failed in Gradio leaves the previous
    request's status in place. txt2img takes no image, so none is read for it.
    """
    from hanaikada.core.errors import HanaikadaError
    from PIL import Image, ImageOps

    nonce = None

    def failed(message: str):
        return None, "", json.dumps({"nonce": nonce, "ok": False, "message": message})

    try:
        request = json.loads(raw or "{}")
        nonce = request.get("nonce")
        target, root_id, path = request["target"], request["root_id"], request["path"]
        infotext = request.get("infotext") or ""
    except (ValueError, KeyError, TypeError, AttributeError):
        return failed("Invalid request")
    ok = json.dumps({"nonce": nonce, "ok": True})
    if target not in TARGETS:
        return failed(f"Unknown target: {target}")
    if target == "txt2img":
        if not infotext.strip():
            return failed("This image has no generation parameters to send to txt2img.")
        return None, infotext, ok
    resources = services_getter()
    if resources is None:
        return failed("Hanaikada is not running.")
    try:
        file = resources.services.library.file_path(str(root_id), str(path))
        with Image.open(file) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except HanaikadaError as error:
        return failed(error.message)
    except OSError as error:
        return failed(f"Cannot read the image: {error}")
    return image, infotext, ok


def build(services_getter: Callable[[], Any]) -> bool:
    """The hidden components and paste bindings, inside the current ``gr.Blocks``.

    Returns False, building nothing, when the host has no paste API (a test fixture). The page
    offers only the targets whose buttons exist.
    """
    import gradio as gr

    try:
        paste = paste_module()
    except ImportError:
        return False
    js = js_keyword(gr.__version__)
    # Hidden by CSS (style.css), not visible=False: Gradio 4 leaves invisible components out of the
    # page, and the page must click these buttons.
    with gr.Group(elem_id=ELEMENT):
        request = gr.Textbox(elem_id=f"{ELEMENT}-request", show_label=False)
        image = gr.Image(type="pil", elem_id=f"{ELEMENT}-image", show_label=False)
        text = gr.Textbox(elem_id=f"{ELEMENT}-text", show_label=False)
        status = gr.Textbox(elem_id=f"{ELEMENT}-status", show_label=False)
        load_button = gr.Button(elem_id=f"{ELEMENT}-load")
        load_button.click(fn=lambda raw: load(raw, services_getter), inputs=[request], outputs=[image, text, status], show_progress=False).then(
            fn=None, **{js: "() => { window.hanaikadaSendLoaded?.(); }"}
        )
        for target in TARGETS:
            # With the infotext, and without it: an empty text would make the WebUI paste the
            # previous generation's parameters (params.txt) instead.
            if target != "extras":
                with_text = gr.Button(elem_id=f"{ELEMENT}-paste-{target}")
                paste.register_paste_params_button(
                    paste.ParamBinding(
                        paste_button=with_text, tabname=target, source_text_component=text, source_image_component=None if target == "txt2img" else image
                    )
                )
            if target != "txt2img":
                image_only = gr.Button(elem_id=f"{ELEMENT}-paste-{target}-image")
                paste.register_paste_params_button(paste.ParamBinding(paste_button=image_only, tabname=target, source_image_component=image))
    return True
