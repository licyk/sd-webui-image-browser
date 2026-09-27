from pathlib import Path

from sd_webui_image_browser.roots import collect_roots, output_folders
from tests.conftest import A1111_OPTIONS, FORGE_OPTIONS, make_host


def reachable(roots):
    """Every folder Hanaikada lists and indexes for these roots, as it computes them."""
    from hanaikada.core.library.layouts import plan_for

    return [(Path(r["path"]) / out.rel).resolve() for r in roots.roots for out in plan_for(r["layout"], Path(r["path"])).outputs]


def covered(folder: Path, roots) -> bool:
    return any(folder == out or out in folder.parents for out in reachable(roots))


def test_a1111_defaults_are_one_webui_root(tmp_path, monkeypatch):
    webui = tmp_path / "stable-diffusion-webui"
    for sub in ("outputs/txt2img-images", "outputs/img2img-images", "log/images"):
        (webui / sub).mkdir(parents=True)
    monkeypatch.chdir(webui)
    shared, paths = make_host(webui, A1111_OPTIONS)
    roots = collect_roots(shared, paths, "Stable Diffusion WebUI")
    assert [(r["name"], r["path"], r["layout"]) for r in roots.roots] == [("Stable Diffusion WebUI", str(webui.resolve()), "sd-webui")]
    assert roots.outputs[0] == (webui / "outputs" / "txt2img-images").resolve()
    assert all(covered(folder, roots) for folder in roots.outputs if folder.exists())
    # Folders the host has not created yet are left to the layout, which lists them once they exist.
    assert not (webui / "outputs" / "extras-images").exists()
    assert collect_roots(shared, paths, "x").roots[0]["id"] == roots.roots[0]["id"]


def test_forge_hires_folder_and_unset_options(tmp_path, monkeypatch):
    webui = tmp_path / "sd-webui-forge-neo"
    (webui / "output" / "txt2img-images").mkdir(parents=True)
    (webui / "output" / "hires").mkdir(parents=True)
    monkeypatch.chdir(webui)
    options = {**FORGE_OPTIONS, "outdir_hires_samples": "output/hires"}
    shared, paths = make_host(webui, options)
    roots = collect_roots(shared, paths, "Forge")
    assert [(r["name"], r["layout"]) for r in roots.roots] == [("Forge", "sd-webui"), ("hires", "custom")]
    assert (webui / "output" / "hires").resolve() in roots.outputs
    assert all(covered(folder, roots) for folder in roots.outputs if folder.exists())
    # A1111 has no hires or video option; an unset Forge hires folder falls back to txt2img.
    shared.opts.data["outdir_hires_samples"] = ""
    assert collect_roots(shared, paths, "Forge").roots[1:] == []
    assert not {"hires", "videos"} & {p.name for p in output_folders(make_host(webui, A1111_OPTIONS)[0].opts, str(webui))}


def test_folders_outside_the_webui_get_roots_of_their_own(tmp_path, monkeypatch):
    webui = tmp_path / "webui"
    elsewhere = tmp_path / "D" / "AI" / "outputs"
    (elsewhere / "grids").mkdir(parents=True)
    options = {**A1111_OPTIONS, "outdir_samples": str(elsewhere), "outdir_grids": str(elsewhere / "grids"), "outdir_save": str(tmp_path / "saved")}
    shared, paths = make_host(webui, options)
    monkeypatch.chdir(webui)
    roots = collect_roots(shared, paths, "Stable Diffusion WebUI")
    # Grids sit inside the common folder; the missing Save folder is listed until the host creates it.
    assert [(r["name"], r["path"], r["layout"]) for r in roots.roots] == [
        ("Stable Diffusion WebUI", str(webui.resolve()), "sd-webui"),
        ("AI", str(elsewhere.resolve()), "custom"),
        ("saved", str((tmp_path / "saved").resolve()), "custom"),
    ]
    assert roots.outputs[:2] == [elsewhere.resolve(), (elsewhere / "grids").resolve()]
    assert all(covered(folder, roots) for folder in roots.outputs if folder.exists())


def test_settings_file_elsewhere_lists_each_output_folder(tmp_path, monkeypatch):
    webui = tmp_path / "webui"
    (webui / "outputs" / "txt2img-images").mkdir(parents=True)
    (webui / "outputs" / "extras-images").mkdir(parents=True)
    monkeypatch.chdir(webui)
    shared, paths = make_host(webui, A1111_OPTIONS, config_filename=tmp_path / "profiles" / "config.json")
    roots = collect_roots(shared, paths, "Stable Diffusion WebUI")
    # Without its config.json the layout could fall back to the whole install, models included.
    assert all(r["layout"] == "custom" for r in roots.roots)
    assert [r["name"] for r in roots.roots][:3] == ["txt2img-images", "img2img-images", "extras-images"]
    assert len(roots.roots) == len(roots.outputs)
    assert all(covered(folder, roots) for folder in roots.outputs if folder.exists())


def test_relative_folders_resolve_from_the_working_directory(tmp_path, monkeypatch):
    # --data-dir below the install: the host resolves "data/outputs/..." from its working directory,
    # while Hanaikada's layout reads the same text relative to the data folder.
    install = tmp_path / "webui"
    data = install / "data"
    (data / "outputs" / "txt2img-images").mkdir(parents=True)
    (install / "custom").mkdir(parents=True)
    monkeypatch.chdir(install)
    options = {key: value.replace("outputs/", "data/outputs/").replace("log/", "data/log/") for key, value in A1111_OPTIONS.items()}
    options["outdir_img2img_samples"] = "custom"
    shared, paths = make_host(data, options)
    roots = collect_roots(shared, paths, "Stable Diffusion WebUI")
    assert (data / "outputs" / "txt2img-images").resolve() in roots.outputs
    assert (install / "custom").resolve() in [Path(r["path"]) for r in roots.roots]
    assert all(covered(folder, roots) for folder in roots.outputs if folder.exists())
