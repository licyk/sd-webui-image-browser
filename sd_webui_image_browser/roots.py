"""Turn the host's effective output settings into Hanaikada image roots."""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

# Each output option, in the order Hanaikada lists a WebUI's folders, with the option the host lets
# override it (``opts.outdir_samples or opts.outdir_txt2img_samples``). Hires and videos exist only
# in Forge; Forge's hires folder falls back to the txt2img one when empty.
OUTPUT_OPTIONS = (
    ("outdir_txt2img_samples", "outdir_samples"),
    ("outdir_hires_samples", None),
    ("outdir_img2img_samples", "outdir_samples"),
    ("outdir_extras_samples", "outdir_samples"),
    ("outdir_txt2img_grids", "outdir_grids"),
    ("outdir_img2img_grids", "outdir_grids"),
    ("outdir_save", None),
    ("outdir_init_images", None),
    ("outdir_videos", "outdir_samples"),
)
_MISSING = object()


@dataclass
class HostRoots:
    roots: list[dict] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    """Every folder the host writes images to, resolved, whether or not it exists yet."""

    def add(self, path: Path, name: str, layout: str) -> dict:
        root = {
            "id": "webui-" + hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()[:16],
            "name": name,
            "path": str(path),
            "layout": layout,
            "enabled": True,
            "index": True,
        }
        self.roots.append(root)
        return root


def _option(opts, key):
    # Real options return their default for unset keys and raise AttributeError for unknown ones.
    try:
        return getattr(opts, key)
    except AttributeError:
        data = getattr(opts, "data", None) or {}
        return data.get(key, _MISSING)


def output_folders(opts, cwd: str) -> list[Path]:
    """The folders the host saves to, relative paths taken from its working directory like it does."""
    out: list[Path] = []
    for key, override in OUTPUT_OPTIONS:
        value = _option(opts, key)
        if value is _MISSING:
            continue
        if override is not None:
            common = _option(opts, override)
            value = common if isinstance(common, str) and common.strip() else value
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(os.path.abspath(os.path.join(cwd, os.path.expanduser(value.strip())))).resolve()
        if path not in out:
            out.append(path)
    return out


def _within(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def collect_roots(shared, paths, host_name: str, cwd: str | None = None) -> HostRoots:
    """The WebUI folder with Hanaikada's ``sd-webui`` layout, plus any output folder it cannot reach.

    The layout reads the same ``config.json`` as the host and follows changes to it without a
    restart. It resolves relative folders from the WebUI folder and skips folders outside it, so
    those, a settings file kept elsewhere (``--ui-settings-file``) and Forge's hires folder get a
    root of their own.
    """
    from hanaikada.core.library.layouts import plan_for
    from hanaikada.core.library.service import default_root_name

    cwd = cwd or os.getcwd()
    roots = HostRoots(outputs=output_folders(shared.opts, cwd))
    data = Path(paths.data_path).resolve()
    config = getattr(shared, "config_filename", None)
    reachable: list[Path] = []
    webui = None
    if config and Path(os.path.abspath(os.path.join(cwd, config))).resolve() == data / "config.json" and data.is_dir():
        webui = roots.add(data, host_name, "sd-webui")
        reachable = [(data / out.rel).resolve() for out in plan_for("sd-webui", data).outputs]

    extra: list[Path] = []
    for folder in roots.outputs:
        if any(_within(folder, other) for other in reachable + extra):
            continue
        # The host creates a folder on its first save; the layout will list it then.
        if webui is not None and not folder.exists() and _within(folder, data):
            continue
        extra.append(folder)
    for folder in extra:
        if not any(other != folder and _within(folder, other) for other in extra):
            roots.add(folder, default_root_name(folder), "custom")
    return roots
