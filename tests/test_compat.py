"""Annotated parameters work on the host's FastAPI, including A1111's 0.94, and only inside the shim."""

from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Body, Depends, FastAPI, Path, Query
from fastapi.dependencies import utils
from fastapi.testclient import TestClient

from sd_webui_image_browser.compat import annotated_parameters, needs_annotated_shim


def service():
    return "service"


Service = Annotated[str, Depends(service)]
Key = Annotated[str, Path(pattern=r"^[a-z]{1,5}$")]


def build():
    router = APIRouter()

    # A dependency first, then a plain parameter: fine once the dependency is a default.
    @router.get("/items/{key}")
    def read(dependency: Service, key: Key, limit: Annotated[int, Query(ge=1, le=10)] = 5, tag: Annotated[list[str] | None, Query()] = None) -> dict:
        return {"dependency": dependency, "key": key, "limit": limit, "tag": tag}

    @router.put("/items/{key}")
    def write(dependency: Service, key: Key, value: Annotated[Any, Body()]) -> dict:
        return {"key": key, "value": value}

    app = FastAPI()
    app.include_router(router)
    return app


def test_routes_read_annotated_parameters():
    original = utils.get_typed_signature
    with annotated_parameters():
        app = build()
    assert utils.get_typed_signature is original
    with TestClient(app) as client:
        assert client.get("/items/abc").json() == {"dependency": "service", "key": "abc", "limit": 5, "tag": None}
        assert client.get("/items/abc", params={"limit": 3, "tag": ["x", "y"]}).json()["tag"] == ["x", "y"]
        assert client.get("/items/abc", params={"limit": 11}).status_code == 422
        assert client.get("/items/ABC123").status_code == 422
        assert client.put("/items/abc", json={"a": [1]}).json() == {"key": "abc", "value": {"a": [1]}}
        assert client.put("/items/abc").status_code == 422


@pytest.mark.skipif(not needs_annotated_shim(), reason="FastAPI reads Annotated itself")
def test_old_fastapi_needs_it_and_the_host_routes_stay_untouched():
    with annotated_parameters():
        build()
    from fastapi.exceptions import FastAPIError

    try:
        app = build()
    except FastAPIError:
        app = None  # Some Annotated types are refused outright ...
    if app is not None:
        with TestClient(app) as client:
            # ... the rest become required query parameters instead of dependencies.
            assert client.get("/items/abc").status_code == 422
    # Shared markers are copied, never modified in place.
    assert Key.__metadata__[0].default is not None and Key.__metadata__[0].regex is None
