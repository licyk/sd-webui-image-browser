import base64
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sd_webui_image_browser.auth import HostAuth


async def content(scope, receive, send):
    await JSONResponse({"ok": True})(scope, receive, send)


def client_for(parent, **kwargs):
    app = FastAPI()
    app.mount("/hub", HostAuth(content, parent, **kwargs))
    return TestClient(app)


@pytest.mark.parametrize("cookie_id", [None, "forge-session"])
def test_gradio_3_and_4_sessions_protect_all_paths_and_websockets(cookie_id):
    parent = SimpleNamespace(auth={"user": "pass"}, tokens={"valid": "user"}, cookie_id=cookie_id)
    with client_for(parent) as client:
        for path in ("/", "/assets/app.js", "/api/v1/app/health", "/_host/status", "/ws/socket.io/?transport=polling"):
            assert client.get("/hub" + path).status_code == 401
        with pytest.raises(WebSocketDisconnect) as error, client.websocket_connect("/hub/ws/socket.io/"):
            pass
        assert error.value.code == 1008
        suffix = f"-{cookie_id}" if cookie_id else ""
        for name in ("access-token", "access-token-unsecure"):
            client.cookies.clear()
            client.cookies.set(name + suffix, "valid")
            assert client.get("/hub/").status_code == 200
        parent.tokens.clear()
        assert client.get("/hub/").status_code == 401


def test_forge_does_not_accept_legacy_session_cookie():
    parent = SimpleNamespace(auth={}, tokens={"valid": "user"}, cookie_id="forge")
    with client_for(parent) as client:
        client.cookies.set("access-token", "valid")
        assert client.get("/hub/").status_code == 401


@pytest.mark.parametrize("asynchronous", [False, True])
def test_external_auth_dependency(asynchronous):
    def dependency(request):
        return "user" if request.headers.get("x-session") == "valid" else None

    async def async_dependency(request):
        return dependency(request)

    parent = SimpleNamespace(auth_dependency=async_dependency if asynchronous else dependency)
    with client_for(parent) as client:
        assert client.get("/hub/").status_code == 401
        assert client.get("/hub/", headers={"x-session": "valid"}).status_code == 200


def test_api_only_uses_api_auth_and_gui_uses_gradio_auth():
    parent = SimpleNamespace()
    auth = "Basic " + base64.b64encode(b"user:pass:with-colon").decode()
    with client_for(parent, api_only=True, api_auth="user:pass:with-colon") as client:
        assert client.get("/hub/").status_code == 401
        assert client.get("/hub/", headers={"Authorization": "Basic !bad"}).status_code == 401
        assert client.get("/hub/", headers={"Authorization": auth}).status_code == 200
    with client_for(parent, api_only=False, api_auth="user:pass") as client:
        assert client.get("/hub/").status_code == 200
    with client_for(parent, api_only=True, api_auth="invalid") as client:
        assert client.get("/hub/").status_code == 401
