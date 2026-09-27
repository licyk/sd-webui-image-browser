import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sd_webui_image_browser import host as host_module

# modules/shared_options.py defaults, as the host writes them into config.json.
A1111_OPTIONS = {
    "outdir_samples": "",
    "outdir_txt2img_samples": "outputs/txt2img-images",
    "outdir_img2img_samples": "outputs/img2img-images",
    "outdir_extras_samples": "outputs/extras-images",
    "outdir_grids": "",
    "outdir_txt2img_grids": "outputs/txt2img-grids",
    "outdir_img2img_grids": "outputs/img2img-grids",
    "outdir_save": "log/images",
    "outdir_init_images": "outputs/init-images",
}
FORGE_OPTIONS = {
    "outdir_samples": "",
    "outdir_txt2img_samples": "output/txt2img-images",
    "outdir_hires_samples": "",
    "outdir_img2img_samples": "output/img2img-images",
    "outdir_extras_samples": "output/extras-images",
    "outdir_videos": "output/videos",
    "outdir_grids": "",
    "outdir_txt2img_grids": "output/txt2img-grids",
    "outdir_img2img_grids": "output/img2img-grids",
    "outdir_save": "output/images",
    "outdir_init_images": "output/init-images",
}
INFOTEXT = "a cherry tree\nNegative prompt: blurry\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 42, Size: 8x8, Model: test"


class Options:
    """Like modules.options.Options: unset options give their default, unknown ones raise."""

    def __init__(self, defaults, data=None):
        self.__dict__.update(defaults=dict(defaults), data=dict(data or {}))

    def __getattr__(self, key):
        if key in self.data:
            return self.data[key]
        if key in self.defaults:
            return self.defaults[key]
        raise AttributeError(key)


def save_png(path: Path, text: str = INFOTEXT) -> Path:
    from PIL import Image, PngImagePlugin

    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", text)
    Image.new("RGB", (8, 8), (200, 80, 120)).save(path, pnginfo=info)
    return path


def make_host(webui: Path, options: dict, *, config: dict | None = None, config_filename: Path | None = None):
    webui.mkdir(parents=True, exist_ok=True)
    config_filename = config_filename or webui / "config.json"
    config_filename.parent.mkdir(parents=True, exist_ok=True)
    config_filename.write_text(json.dumps(options if config is None else config), encoding="utf-8")
    shared = SimpleNamespace(
        cmd_opts=SimpleNamespace(listen=False, share=False, api_auth=None),
        opts=Options(options),
        config_filename=str(config_filename),
    )
    paths = SimpleNamespace(data_path=str(webui), models_path=str(webui / "models"))
    return shared, paths


@pytest.fixture
def host(tmp_path, monkeypatch):
    """An A1111 install with one generated image, started from its own folder like the host."""
    monkeypatch.setattr(host_module, "DATA_DIR", tmp_path / "extension" / "data")
    webui = tmp_path / "stable-diffusion-webui"
    save_png(webui / "outputs" / "txt2img-images" / "2026-09-27" / "00000-42.png")
    (webui / "models" / "Stable-diffusion").mkdir(parents=True)
    save_png(webui / "models" / "Stable-diffusion" / "preview.png")
    monkeypatch.chdir(webui)
    shared, paths = make_host(webui, A1111_OPTIONS)
    return shared, paths
