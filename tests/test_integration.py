import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hanaikada.core.events.models import LibraryChangedEvent
from starlette import _utils

from sd_webui_image_browser.compat import annotated_parameters
from sd_webui_image_browser.host import create_factory, image_saved, mount_browser
from tests.conftest import save_png

NEW_PROMPT = "a paper lantern\nSteps: 12, Sampler: DPM++ 2M, Schedule type: Karras, CFG scale: 5, Seed: 7, Size: 8x8, Model: test"


@pytest.fixture
def dist(tmp_path, monkeypatch):
    # Hanaikada declares its routes on import; on A1111's FastAPI that needs the shim, as in the host.
    with annotated_parameters():
        from hanaikada.api import app, static

    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text('<script src="./assets/app.js"></script>')
    (directory / "assets" / "app.js").write_text("window.hanaikadaLoaded = true;")
    monkeypatch.setattr(app, "web_dist_dir", lambda: directory)
    monkeypatch.setattr(static, "web_dist_dir", lambda: directory)
    return directory


def search(client, base, text):
    response = client.post(f"{base}/api/v1/search", json={"text": text})
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def test_mount_after_startup_prefix_auth_roots_socket_and_shutdown(host, dist):
    shared, paths = host
    parent = FastAPI()
    parent.auth = {"user": "password"}
    parent.tokens = {"valid": "user"}
    parent.cookie_id = "forge"
    # Emulate a reverse proxy / --subpath, with old/new Starlette scope semantics.
    base = "/webui/hanaikada" if hasattr(_utils, "get_route_path") else "/hanaikada"
    with TestClient(parent, base_url="http://localhost", root_path="/webui") as client:
        runtime = mount_browser(SimpleNamespace(server_port=7860), parent, shared, paths)
        assert mount_browser(None, parent, shared, paths) is runtime
        assert runtime.task is None
        denied = client.get(f"{base}/_host/status")
        assert denied.status_code == 401
        assert denied.headers["content-security-policy"] == "frame-ancestors 'self'"
        assert runtime.task is None  # Unauthenticated users cannot start the scanner.
        client.cookies.set("access-token-forge", "valid")
        status = client.get(f"{base}/_host/status")
        assert status.status_code == 200, status.text
        body = status.json()
        assert body["ui_available"] and body["combined_view"] and body["host"] == "A1111"
        assert [(r["name"], r["layout"]) for r in body["roots"]] == [("Stable Diffusion WebUI", "sd-webui")]
        page = client.get(f"{base}/", headers={"accept": "text/html"})
        assert page.text == '<script src="./assets/app.js"></script>'
        # Overrides a proxy's X-Frame-Options: DENY so the WebUI tab can frame Hanaikada.
        assert page.headers["content-security-policy"] == "frame-ancestors 'self'"
        assert client.get(f"{base}/assets/app.js").status_code == 200
        assert client.get(f"{base}/api/v1/app/meta").json()["roots_locked"]
        assert client.get(f"{base}/api/v1/app/health").json()["auth_required"] is False
        assert client.post(f"{base}/api/v1/library/roots", json={"path": paths.models_path}).status_code == 409
        assert client.patch(f"{base}/api/v1/settings", json={}, headers={"Origin": "http://evil.example"}).status_code == 403
        assert client.get(f"{base}/_host/status", headers={"Host": "evil.example"}).status_code == 400

        services = runtime.services.services
        assert services.index.wait_idle(20)
        root_id = body["default_root"]
        # The start-up scan indexed the output folder, and nothing else of the install.
        assert search(client, base, "cherry") == ["00000-42.png"]
        listing = client.get(f"{base}/api/v1/library/roots/{root_id}/entries", params={"path": "outputs/txt2img-images/2026-09-27"}).json()
        assert [(f["name"], f["indexed"]) for f in listing["files"]] == [("00000-42.png", True)]
        assert client.get(f"{base}/api/v1/library/roots/{root_id}/entries", params={"path": "models"}).status_code in (400, 404)
        thumbnail = client.get(
            f"{base}/api/v1/library/roots/{root_id}/thumbnail", params={"path": "outputs/txt2img-images/2026-09-27/00000-42.png", "size": 128}
        )
        assert thumbnail.status_code == 200 and thumbnail.headers["content-type"] == "image/webp"

        polling = client.get(f"{base}/ws/socket.io/?EIO=4&transport=polling")
        assert polling.status_code == 200 and polling.text.startswith('0{"sid":')
        with client.websocket_connect(f"ws://localhost{base}/ws/socket.io/?EIO=4&transport=websocket", headers={"Upgrade": "websocket"}) as socket:
            assert socket.receive_text().startswith('0{"sid":')
            socket.send_text("40")
            assert socket.receive_text().startswith("40")
            services.events.publish(LibraryChangedEvent(root_id=root_id, rel_path="outputs"))
            assert socket.receive_text().startswith('42["library_changed",')
        scanner = services.index.scanner
    assert runtime.closed and runtime.task.done()
    assert not scanner.running


def test_saved_images_are_indexed_at_once(host, dist):
    shared, paths = host
    parent = FastAPI()
    runtime = mount_browser(object(), parent, shared, paths)
    image = Path(paths.data_path) / "outputs" / "txt2img-images" / "2026-09-27" / "00001-7.png"
    params = SimpleNamespace(image=SimpleNamespace(), filename=str(image.with_name("00001-7-renamed.png")))
    image_saved(runtime, params)  # Not started yet: nothing to do, the start-up scan will see it.
    with TestClient(parent, base_url="http://localhost") as client:
        base = "/hanaikada"
        assert client.get(f"{base}/_host/status").status_code == 200
        services = runtime.services.services
        assert services.index.wait_idle(20)
        # Watching is slow by default; only the hook can index the file this quickly.
        assert services.settings.settings.index.watch_interval >= 30
        save_png(image, NEW_PROMPT)
        params.image.already_saved_as = str(image)  # The name the host settled on after the callback's.
        image_saved(runtime, params)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not search(client, base, "lantern"):
            time.sleep(0.05)
        assert search(client, base, "lantern") == ["00001-7.png"]
        image_saved(runtime, SimpleNamespace(image=None, filename=str(Path(paths.models_path) / "outside.png")))
    assert runtime.closed
    image_saved(runtime, params)


def test_forge_host_and_public_url(host, dist):
    shared, paths = host
    shared.opts.data["hanaikada_public_url"] = "https://images.example/webui/hanaikada"
    resources, app = create_factory(shared, paths, None, {"modules_forge.main_entry": object()})()
    try:
        with TestClient(app, base_url="https://images.example") as client:
            status = client.get("/_host/status").json()
            assert status["host"] == "Forge" and status["roots"][0]["name"] == "Forge"
            assert client.get("/_host/status", headers={"Host": "other.example"}).status_code == 400
    finally:
        resources.close()


def test_all_folders_is_pinned_and_lists_output_folders(host, dist):
    shared, paths = host
    save_png(Path(paths.data_path) / "log" / "images" / "saved.png")
    resources, app = create_factory(shared, paths, None, {})()
    try:
        with TestClient(app, base_url="http://localhost") as client:
            combined = client.get("/api/v1/library/combined/entries")
            assert combined.status_code == 200, combined.text
            assert [(f["name"], f["label"]) for f in combined.json()["folders"]] == [("txt2img-images", "txt2img"), ("images", "saved")]
            client.patch("/api/v1/settings", json={"library": {"combined_view": False}})
            assert client.get("/_host/status").json()["combined_view"] is True
    finally:
        resources.close()


def test_settings_persist_in_extension_data_directory(host, dist, tmp_path):
    shared, paths = host
    data_dir = tmp_path / "extension" / "data"
    factory = create_factory(shared, paths, None, {})
    resources, app = factory()
    try:
        with TestClient(app, base_url="http://localhost") as client:
            response = client.patch("/api/v1/settings", json={"index": {"prompt_tag_min_count": 3}})
            assert response.status_code == 200, response.text
            assert resources.services.settings.data_dir == data_dir
            assert (data_dir / "settings.toml").is_file()
            assert (data_dir / "hanaikada.db").is_file()
            assert not (Path(paths.data_path) / "hanaikada").exists()
    finally:
        resources.close()

    resources, _app = factory()
    try:
        assert resources.services.settings.settings.index.prompt_tag_min_count == 3
    finally:
        resources.close()
