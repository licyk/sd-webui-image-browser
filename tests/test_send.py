"""Send to txt2img / img2img / inpaint / extras: the load step and the paste bindings."""

import json
import sys
from types import SimpleNamespace

import pytest
from hanaikada.core.context import build_services
from hanaikada.core.library.models import RootCreate
from PIL import Image

from sd_webui_image_browser import send
from tests.conftest import INFOTEXT, save_png


@pytest.fixture
def resources(tmp_path):
    folder = tmp_path / "outputs"
    save_png(folder / "00000-42.png")
    Image.new("RGB", (4, 2)).save(folder / "wide.jpg")
    services = build_services(data_dir=tmp_path / "data", environ={})
    root = services.library.add_root(RootCreate(path=str(folder), name="outputs", layout="custom", index=False))
    yield SimpleNamespace(services=services, root_id=root.id)
    services.close()


def request(target, root_id, path, infotext=INFOTEXT):
    return json.dumps({"nonce": "n1", "target": target, "root_id": root_id, "path": path, "infotext": infotext})


def test_gradio_names_the_front_end_function():
    assert send.js_keyword("3.41.2") == "_js"
    assert send.js_keyword("4.40.0") == "js"


def test_img2img_gets_the_image_and_the_infotext(resources):
    image, text, status = send.load(request("img2img", resources.root_id, "wide.jpg"), lambda: resources)
    assert image.size == (4, 2) and text == INFOTEXT and json.loads(status) == {"nonce": "n1", "ok": True}


def test_txt2img_gets_only_the_parameters(resources):
    image, text, status = send.load(request("txt2img", resources.root_id, "00000-42.png"), lambda: resources)
    assert image is None and text == INFOTEXT and json.loads(status)["ok"]
    _, _, status = send.load(request("txt2img", resources.root_id, "00000-42.png", infotext=""), lambda: resources)
    assert json.loads(status) == {"nonce": "n1", "ok": False, "message": "This image has no generation parameters to send to txt2img."}


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "Invalid request"),
        (json.dumps({"target": "img2img"}), "Invalid request"),
        (request("controlnet", "x", "a.png"), "Unknown target: controlnet"),
    ],
)
def test_bad_requests(resources, raw, message):
    image, _, status = send.load(raw, lambda: resources)
    assert image is None and json.loads(status)["ok"] is False and json.loads(status)["message"] == message


def test_only_files_inside_a_root_are_read(resources, tmp_path):
    Image.new("RGB", (2, 2)).save(tmp_path / "secret.png")
    for path in ("../secret.png", "missing.png"):
        image, _, status = send.load(request("img2img", resources.root_id, path), lambda: resources)
        assert image is None and json.loads(status)["ok"] is False
    _, _, status = send.load(request("img2img", "nope", "00000-42.png"), lambda: resources)
    assert json.loads(status)["ok"] is False
    _, _, status = send.load(request("img2img", resources.root_id, "00000-42.png"), lambda: None)
    assert json.loads(status) == {"nonce": "n1", "ok": False, "message": "Hanaikada is not running."}


def test_paste_buttons_are_registered_for_each_tab(monkeypatch):
    gr = pytest.importorskip("gradio")
    bindings = []

    class ParamBinding:
        def __init__(self, paste_button, tabname, source_text_component=None, source_image_component=None):
            self.paste_button, self.tabname, self.text, self.image = paste_button, tabname, source_text_component, source_image_component

    monkeypatch.setattr(send, "paste_module", lambda: SimpleNamespace(ParamBinding=ParamBinding, register_paste_params_button=bindings.append))
    with gr.Blocks() as demo:
        assert send.build(lambda: None)
    shape = [(b.tabname, b.paste_button.elem_id, b.text is not None, b.image is not None) for b in bindings]
    assert shape == [
        ("txt2img", "hanaikada-send-paste-txt2img", True, False),
        ("img2img", "hanaikada-send-paste-img2img", True, True),
        ("img2img", "hanaikada-send-paste-img2img-image", False, True),
        ("inpaint", "hanaikada-send-paste-inpaint", True, True),
        ("inpaint", "hanaikada-send-paste-inpaint-image", False, True),
        ("extras", "hanaikada-send-paste-extras-image", False, True),
    ]
    # After loading, the page is told, through the front-end function of this Gradio version.
    assert any("hanaikadaSendLoaded" in (dependency.get("js") or "") for dependency in demo.config["dependencies"])


def test_nothing_is_built_without_the_paste_api(monkeypatch):
    gr = pytest.importorskip("gradio")
    monkeypatch.setitem(sys.modules, "modules", None)
    with gr.Blocks():
        assert send.build(lambda: None) is False
