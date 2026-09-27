"""Connect Hanaikada to the WebUI's output folders, login and UI lifecycle."""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from sd_webui_image_browser import MOUNT_PATH, VERSION
from sd_webui_image_browser.auth import HostAuth
from sd_webui_image_browser.compat import annotated_parameters
from sd_webui_image_browser.roots import HostRoots, collect_roots
from sd_webui_image_browser.runtime import MountedRuntime

logger = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

if TYPE_CHECKING:
    from hanaikada.core.context import Services


def is_forge(loaded) -> bool:
    return "modules_forge.main_entry" in loaded or "modules_forge.shared" in loaded


@dataclass
class Resources:
    services: "Services"
    roots: HostRoots

    def image_saved(self, filename: str) -> None:
        """Index a freshly saved image ahead of the folder watcher, so it appears at once."""
        from hanaikada.core.errors import HanaikadaError

        try:
            ref = self.services.library.locate(Path(os.path.abspath(filename)))
        except HanaikadaError:
            return
        self.services.index.queue_files(ref.root_id, [ref.path])

    def close(self):
        self.services.close()


def create_factory(shared, paths, demo, loaded=None):
    loaded = sys.modules if loaded is None else loaded

    def factory():
        # Hanaikada declares its routes when its API modules are imported.
        with annotated_parameters():
            from hanaikada.api.app import create_app
        from hanaikada.api.paths import validate_public_base_url
        from hanaikada.api.static import web_dist_dir
        from hanaikada.core.context import build_services
        from hanaikada.version import VERSION as HANAIKADA_VERSION

        cmd = shared.cmd_opts
        public_url = validate_public_base_url(shared.opts.data.get("hanaikada_public_url") or None)
        bound_host = getattr(cmd, "server_name", None) or ("0.0.0.0" if getattr(cmd, "listen", False) or getattr(cmd, "share", False) else "127.0.0.1")
        port = getattr(demo, "server_port", None) or getattr(cmd, "port", None) or 7860
        extra_hosts = {urlsplit(public_url).hostname} if public_url else set()
        host = "Forge" if is_forge(loaded) else "A1111"
        roots = collect_roots(shared, paths, "Forge" if host == "Forge" else "Stable Diffusion WebUI")
        services = build_services(
            data_dir=DATA_DIR,
            settings_path=DATA_DIR / "settings.toml",
            roots_locked=True,
            settings_overrides={
                "paths": {"roots": roots.roots},
                # Browse opens on "All folders": every output folder side by side.
                "library": {"combined_view": True},
                "server": {"host": bound_host, "port": port, "access_token": None, "allowed_origins": [], "open_browser": False},
            },
        )
        try:
            with annotated_parameters():
                app = create_app(services, bound_host=bound_host, bound_port=port, extra_hosts=extra_hosts, public_base_url=public_url)

            async def status(_request):
                return JSONResponse(
                    {
                        "extension_version": VERSION,
                        "hanaikada_version": HANAIKADA_VERSION,
                        "host": host,
                        "roots": [{key: root[key] for key in ("id", "name", "path", "layout")} for root in roots.roots],
                        "default_root": roots.roots[0]["id"] if roots.roots else None,
                        "combined_view": services.settings.settings.library.combined_view,
                        "ui_available": (web_dist_dir() / "index.html").is_file(),
                    },
                    headers={"Cache-Control": "no-store"},
                )

            # Precede the web UI's catch-all mount; Hanaikada's security middleware also protects
            # this route, including Host validation.
            app.router.routes.insert(0, Route("/_host/status", status, methods=["GET"]))
        except BaseException:
            services.close()
            raise
        return Resources(services, roots), app

    return factory


class SameOriginFrames:
    """Let the WebUI page frame Hanaikada even when a reverse proxy adds ``X-Frame-Options: DENY``.

    Browsers ignore ``X-Frame-Options`` when a response carries a CSP ``frame-ancestors``
    directive. A separate CSP header only adds restrictions, so any policy the proxy or Hanaikada
    sends still applies.
    """

    header = (b"content-security-policy", b"frame-ancestors 'self'")

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), self.header]}
            await send(message)

        await self.app(scope, receive, send_with_header)


def mount_browser(demo, app, shared, paths):
    existing = getattr(app.state, "sd_webui_image_browser", None)
    if existing is not None:
        return existing
    if any(getattr(route, "path", None) == MOUNT_PATH for route in app.routes):
        raise RuntimeError(f"Another application already occupies {MOUNT_PATH}")
    runtime = MountedRuntime(create_factory(shared, paths, demo))
    guarded = HostAuth(runtime, app, api_only=demo is None, api_auth=getattr(shared.cmd_opts, "api_auth", None))
    # Insert before any host catch-all route, without changing the host's middleware.
    app.router.routes.insert(0, Mount(MOUNT_PATH, SameOriginFrames(guarded), name="sd-webui-image-browser"))
    app.add_event_handler("shutdown", runtime.shutdown)
    app.state.sd_webui_image_browser = runtime
    return runtime


def image_saved(runtime, params):
    """``on_image_saved``: runs on the generation thread once the file and its ``.txt`` are written."""
    resources = runtime.services if runtime is not None and not runtime.closed else None
    if resources is None:
        return  # Nobody has opened the browser yet; the start-up scan will find the file.
    # The host may pick another name after the callback's filename was decided.
    filename = getattr(params.image, "already_saved_as", None) or params.filename
    if filename:
        resources.image_saved(filename)


def on_ui_settings():
    from modules import shared

    section = ("hanaikada", "Hanaikada")
    shared.opts.add_option(
        "hanaikada_public_url",
        shared.OptionInfo("", "反向代理外部地址（含 /hanaikada；修改后重启 WebUI）", section=section),
    )


def on_ui_tabs(resources_getter=None):
    """The Hanaikada tab. ``resources_getter`` returns the running ``Resources`` (or None); with it,
    the tab also carries the hidden parts of "Send to txt2img / img2img / inpaint / extras"."""
    import gradio as gr

    from sd_webui_image_browser.send import build

    with gr.Blocks(analytics_enabled=False) as tab:
        gr.HTML(
            """<div id="hanaikada-panel">
  <p class="hanaikada-status" role="status" aria-live="polite" hidden></p>
  <iframe title="Hanaikada 图片浏览和管理" class="hanaikada-frame" hidden></iframe>
</div>"""
        )
        if resources_getter is not None:
            build(resources_getter)
    return [(tab, "Hanaikada", "hanaikada")]
