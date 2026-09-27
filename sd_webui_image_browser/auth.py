"""Apply the host's login to every mounted HTTP and WebSocket request."""

import base64
import binascii
import hmac
import inspect

from starlette.requests import HTTPConnection, Request
from starlette.responses import JSONResponse


class HostAuth:
    def __init__(self, app, parent, *, api_only: bool = False, api_auth: str | None = None):
        self.app = app
        self.parent = parent
        self.api_only = api_only
        self.api_auth_configured = bool(api_auth)
        self.credentials = [entry.split(":", 1) for entry in (api_auth or "").split(",") if ":" in entry]

    async def allowed(self, scope) -> bool:
        dependency = getattr(self.parent, "auth_dependency", None)
        if dependency is not None:
            # Gradio auth dependencies operate on HTTP cookies/headers, also for sockets.
            request = Request(dict(scope, type="http", method=scope.get("method", "GET")))
            user = dependency(request)
            if inspect.isawaitable(user):
                user = await user
            return user is not None
        connection = HTTPConnection(scope)
        if getattr(self.parent, "auth", None) is not None:
            cookie_id = getattr(self.parent, "cookie_id", None)
            suffix = f"-{cookie_id}" if cookie_id else ""
            tokens = getattr(self.parent, "tokens", {})
            return any(tokens.get(connection.cookies.get(name + suffix)) is not None for name in ("access-token", "access-token-unsecure"))
        if self.api_only and self.api_auth_configured:
            scheme, _, encoded = connection.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "basic":
                return False
            try:
                user, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            except (ValueError, UnicodeError, binascii.Error):
                return False
            return any(
                hmac.compare_digest(user.encode(), name.encode()) & hmac.compare_digest(password.encode(), secret.encode()) for name, secret in self.credentials
            )
        return True

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and not await self.allowed(scope):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                headers = {"WWW-Authenticate": 'Basic realm="Hanaikada"'} if self.api_only and self.api_auth_configured else None
                await JSONResponse({"detail": "WebUI login required"}, status_code=401, headers=headers)(scope, receive, send)
            return
        await self.app(scope, receive, send)
