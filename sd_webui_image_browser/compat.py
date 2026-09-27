"""Let FastAPI releases before 0.95 register Hanaikada's routes.

Stable Diffusion WebUI (A1111) pins ``fastapi==0.94.0`` and reinstalls it on every launch, but
Hanaikada declares parameters as ``Annotated[T, Depends(...)]`` / ``Annotated[T, Query()]``, which
FastAPI only reads from 0.95 on. While Hanaikada builds its routes, those parameters are rewritten
into the older ``name: T = Depends(...)`` form. Routes are analysed once, when they are created, so
the patch is removed afterwards and never touches the host's own routes.
"""

import copy
import inspect
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, get_args, get_origin

_lock = threading.Lock()


def needs_annotated_shim() -> bool:
    from fastapi import __version__
    from packaging.version import Version

    return Version(__version__) < Version("0.95")


def _legacy_parameter(param: inspect.Parameter) -> inspect.Parameter:
    if get_origin(param.annotation) is not Annotated:
        return param
    from fastapi import params
    from pydantic.fields import FieldInfo

    base, *metadata = get_args(param.annotation)
    marker = next((m for m in reversed(metadata) if isinstance(m, (params.Depends, FieldInfo))), None)
    if marker is None:
        return param
    if isinstance(marker, params.Depends):
        return param.replace(annotation=base, default=marker)
    # Markers are shared by every route using the same alias, so each parameter gets its own copy.
    field = copy.copy(marker)
    field.extra = dict(getattr(marker, "extra", {}))
    if param.default is not inspect.Parameter.empty:
        field.default = param.default
    # FastAPI 0.100 renamed ``regex`` to ``pattern``; older releases keep it as schema-only extra.
    pattern = field.extra.pop("pattern", None)
    if pattern is not None and not getattr(field, "regex", None):
        field.regex = pattern
    return param.replace(annotation=base, default=field)


@contextmanager
def annotated_parameters() -> Iterator[None]:
    """Build routes with ``Annotated`` parameters on any supported FastAPI release."""
    if not needs_annotated_shim():
        yield
        return
    from fastapi.dependencies import utils

    with _lock:
        original = utils.get_typed_signature

        def get_typed_signature(call):
            signature = original(call)
            # A dependency may now carry a default ahead of a plain parameter; FastAPI only reads
            # the parameters, so skip the ordering check a regular signature would make.
            return inspect.Signature(
                [_legacy_parameter(p) for p in signature.parameters.values()],
                return_annotation=signature.return_annotation,
                __validate_parameters__=False,
            )

        utils.get_typed_signature = get_typed_signature
        try:
            yield
        finally:
            utils.get_typed_signature = original
