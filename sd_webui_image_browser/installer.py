"""Small, idempotent launcher installer, without importing Hanaikada.

The host pins its own stack and reinstalls it on the next launch (A1111 keeps ``Pillow==9.5.0``,
``fastapi==0.94.0`` and ``httpcore==0.15``), so upgrading a package the host already has breaks it
or makes the launcher reinstall its requirements every time. pip does not weigh installed packages
it is not asked about: a plain install of python-socketio brings the newest wsproto and with it
``h11>=0.16``, which httpcore 0.15 refuses. Our requirements are installed without dependencies,
then only the missing dependencies are added, resolved against the versions already installed.
Installed packages are never upgraded.
"""

import importlib
import re
import tempfile
from importlib.metadata import PackageNotFoundError, distributions, version
from pathlib import Path

from .package_analyzer import (
    ParsedPyWhlRequirement,
    PyWhlVersionComparison,
    check_version_constraint,
    evaluate_marker,
    get_categorized_dependencies,
    get_parse_bindings,
    normalize_package_name,
    parse_requirement,
)

LABEL = "SD WebUI Image Browser"


def _parse(requirement: str) -> ParsedPyWhlRequirement:
    return parse_requirement(requirement, get_parse_bindings())


def _read(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"(^|\s+)#.*$", "", line).strip()
        if line and evaluate_marker(_parse(line).marker):
            out.append(line)
    return out


def _installed(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _dependencies(name: str) -> list[str]:
    # Optional dependency groups are kept apart, and markers are already evaluated.
    return get_categorized_dependencies(name)["mandatory"]


def _specifier(requirement: str) -> str:
    specifier = _parse(requirement).specifier
    return specifier if isinstance(specifier, str) else ",".join(op + ver for op, ver in specifier)


def _satisfied(requirement: str, installed: str | None) -> bool:
    if installed is None:
        return False
    specifier = _parse(requirement).specifier
    if isinstance(specifier, str):
        return True  # A URL requirement names no version.
    cmp = PyWhlVersionComparison(installed)
    try:
        return all(check_version_constraint(installed, op, ver, cmp) for op, ver in specifier)
    except ValueError:
        return False  # The installed version is not PEP 440.


def _pins(exclude: set[str]) -> list[str]:
    """Every installed distribution at its current version, the first one on sys.path winning."""
    seen = set(exclude)
    pins = []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name or normalize_package_name(name) in seen:
            continue
        seen.add(normalize_package_name(name))
        if not PyWhlVersionComparison.WHL_VERSION_PARSE_REGEX.match(dist.version):
            continue
        pins.append(f"{name}=={dist.version}")
    return pins


def install_requirements(path: Path, run_pip, log=print) -> None:
    for requirement in _read(path):
        name = _parse(requirement).name
        if _satisfied(requirement, _installed(name)):
            continue
        # The requirements file is shipped with the extension, not user input.
        run_pip(f'install --no-deps "{requirement}"', f"{LABEL}: {requirement}")
        importlib.invalidate_caches()
        if _installed(name) is None:
            continue  # --skip-install
        missing, older = [], []
        for dependency in _dependencies(name):
            dependency_name = _parse(dependency).name
            current = _installed(dependency_name)
            if current is None:
                missing.append(dependency)
            elif not _satisfied(dependency, current):
                older.append(f"{dependency_name} {current} ({_specifier(dependency)})")
        if missing:
            with tempfile.TemporaryDirectory() as tmp:
                constraints = Path(tmp) / "constraints.txt"
                exclude = {normalize_package_name(_parse(r).name) for r in (requirement, *missing)}
                constraints.write_text("\n".join(_pins(exclude)) + "\n", encoding="utf-8")
                names = " ".join(f'"{r}"' for r in missing)
                run_pip(f'install {names} -c "{constraints}"', f"{LABEL}: dependencies of {name}")
        if older:
            log(f"{LABEL}: keeping the WebUI's installed {', '.join(older)} for {name}.")
