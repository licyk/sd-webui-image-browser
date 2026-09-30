"""WebUI callback entry point; Hanaikada is loaded lazily."""

import logging

from modules import paths_internal, script_callbacks, shared

from sd_webui_image_browser.host import access_urls, image_saved, mount_browser, on_ui_settings, on_ui_tabs

_runtime = None


def on_app_started(demo, app):
    global _runtime
    try:
        _runtime = mount_browser(demo, app, shared, paths_internal)
    except Exception:
        logging.getLogger(__name__).exception("Could not mount Hanaikada")
        return
    for url in access_urls(demo, shared):
        print(f"SD WebUI Image Browser: {url}")


def on_image_saved(params):
    try:
        image_saved(_runtime, params)
    except Exception:
        logging.getLogger(__name__).exception("Could not index a saved image")


def on_unloaded():
    global _runtime
    if _runtime is not None:
        _runtime.unload()
        _runtime = None


script_callbacks.on_ui_settings(on_ui_settings)


def resources():
    """What Hanaikada is running with, once the browser has been opened."""
    return _runtime.services if _runtime is not None and not _runtime.closed else None


script_callbacks.on_ui_tabs(lambda: on_ui_tabs(resources))
script_callbacks.on_app_started(on_app_started)
script_callbacks.on_image_saved(on_image_saved)
script_callbacks.on_script_unloaded(on_unloaded)
