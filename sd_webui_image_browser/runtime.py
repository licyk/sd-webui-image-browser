"""Own a mounted application's lifespan on the already running WebUI event loop."""

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class MountedRuntime:
    def __init__(self, factory: Callable):
        self.factory = factory
        self.app = None
        self.services = None
        self.task = None
        self.loop = None
        self.ready = None
        self.stop = None
        self.error = None
        self.closed = False

    async def _run(self):
        assert self.ready is not None and self.stop is not None
        try:
            self.services, self.app = self.factory()
            async with self.app.router.lifespan_context(self.app):
                self.ready.set()
                await self.stop.wait()
        except asyncio.CancelledError:
            # Uvicorn cancels outstanding tasks on loop shutdown, including Gradio versions
            # whose custom lifespan does not call app.on_shutdown handlers.
            raise
        except Exception:
            self.error = "Hanaikada 启动失败，请查看 WebUI 控制台并重启 WebUI。"
            logger.exception("Hanaikada startup/lifespan failed")
        finally:
            self.closed = True
            try:
                if self.services is not None:
                    self.services.close()
            finally:
                self.ready.set()

    async def ensure_started(self):
        if self.task is None and not self.closed:
            self.loop = asyncio.get_running_loop()
            self.ready = asyncio.Event()
            self.stop = asyncio.Event()
            self.task = self.loop.create_task(self._run(), name="sd-webui-image-browser")
        if self.ready is not None:
            await self.ready.wait()

    async def shutdown(self):
        self.closed = True
        if self.task is not None:
            assert self.stop is not None
            self.stop.set()
            try:
                await asyncio.shield(self.task)
            except asyncio.CancelledError:
                if not self.task.cancelled():
                    raise

    def unload(self):
        """The script-unloaded callback runs on the WebUI main thread after server.close()."""
        if self.task is not None and not self.task.done() and self.loop is not None and self.loop.is_running():
            assert self.stop is not None
            if self.loop is _running_loop():
                self.stop.set()
            else:
                future = asyncio.run_coroutine_threadsafe(self.shutdown(), self.loop)
                try:
                    future.result(timeout=30)
                # Before Python 3.11 this is not the builtin TimeoutError.
                except concurrent.futures.TimeoutError:
                    logger.warning("Hanaikada is still stopping its scanner")
        else:
            self.closed = True

    async def __call__(self, scope, receive, send):
        await self.ensure_started()
        if self.error or self.closed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1011})
            else:
                await JSONResponse({"detail": self.error or "Hanaikada 已关闭，请刷新 WebUI。"}, status_code=503)(scope, receive, send)
            return
        assert self.app is not None
        await self.app(scope, receive, send)


def _running_loop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
