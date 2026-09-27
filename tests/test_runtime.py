import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI

from sd_webui_image_browser.runtime import MountedRuntime


def test_concurrent_first_requests_have_one_lifespan_and_close_once():
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        events.append("start")
        try:
            yield
        finally:
            events.append("stop")

    def factory():
        events.append("build")
        return SimpleNamespace(close=lambda: events.append("close")), FastAPI(lifespan=lifespan)

    runtime = MountedRuntime(factory)

    async def run():
        await asyncio.gather(*(runtime.ensure_started() for _ in range(10)))
        assert events == ["build", "start"]
        await runtime.shutdown()
        await runtime.shutdown()
        await runtime.ensure_started()

    asyncio.run(run())
    assert events == ["build", "start", "stop", "close"]


def test_gradio_custom_lifespan_loop_cancellation_closes_child():
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            events.append("stop")

    runtime = MountedRuntime(lambda: (SimpleNamespace(close=lambda: events.append("close")), FastAPI(lifespan=lifespan)))
    asyncio.run(runtime.ensure_started())  # asyncio.run cancels outstanding tasks on exit.
    assert events == ["stop", "close"]
    runtime.unload()
    assert events == ["stop", "close"]


def test_initialization_failure_does_not_retry_and_leak(caplog):
    calls = []

    def factory():
        calls.append(1)
        raise ImportError("missing library")

    runtime = MountedRuntime(factory)

    async def run():
        await runtime.ensure_started()
        await runtime.ensure_started()
        await runtime.shutdown()

    asyncio.run(run())
    assert len(calls) == 1 and runtime.error and runtime.closed
    assert "missing library" in caplog.text


def test_unload_from_another_thread_waits_for_shutdown():
    import threading

    events = []

    @asynccontextmanager
    async def lifespan(_app):
        yield
        events.append("stop")

    runtime = MountedRuntime(lambda: (SimpleNamespace(close=lambda: events.append("close")), FastAPI(lifespan=lifespan)))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        asyncio.run_coroutine_threadsafe(runtime.ensure_started(), loop).result(10)
        runtime.unload()  # The WebUI main thread, while the server loop still runs.
        assert events == ["stop", "close"] and runtime.task.done()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)
        loop.close()
