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
import tempfile
from importlib.metadata import PackageNotFoundError, distributions, requires, version
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

LABEL = "SD WebUI Image Browser"


def _read(path: Path) -> list[Requirement]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirement = Requirement(line)
            if not requirement.marker or requirement.marker.evaluate():
                out.append(requirement)
    return out


def _installed(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _dependencies(name: str) -> list[Requirement]:
    out = []
    for line in requires(name) or ():
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            continue
        # Evaluating with an empty extra drops the optional dependency groups.
        if not requirement.marker or requirement.marker.evaluate({"extra": ""}):
            out.append(requirement)
    return out


def _pins(exclude: set[str]) -> list[str]:
    """Every installed distribution at its current version, the first one on sys.path winning."""
    seen = set(exclude)
    pins = []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name or canonicalize_name(name) in seen:
            continue
        seen.add(canonicalize_name(name))
        try:
            Version(dist.version)
        except InvalidVersion:
            continue
        pins.append(f"{name}=={dist.version}")
    return pins


def install_requirements(path: Path, run_pip, log=print) -> None:
    for requirement in _read(path):
        installed = _installed(requirement.name)
        if installed is not None and requirement.specifier.contains(installed, prereleases=True):
            continue
        # The requirements file is shipped with the extension, not user input.
        run_pip(f'install --no-deps "{requirement}"', f"{LABEL}: {requirement}")
        importlib.invalidate_caches()
        if _installed(requirement.name) is None:
            continue  # --skip-install
        missing, older = [], []
        for dependency in _dependencies(requirement.name):
            current = _installed(dependency.name)
            if current is None:
                missing.append(dependency)
            elif not dependency.specifier.contains(current, prereleases=True):
                older.append(f"{dependency.name} {current} ({dependency.specifier})")
        if missing:
            with tempfile.TemporaryDirectory() as tmp:
                constraints = Path(tmp) / "constraints.txt"
                constraints.write_text("\n".join(_pins({canonicalize_name(r.name) for r in (requirement, *missing)})) + "\n", encoding="utf-8")
                names = " ".join(f'"{r}"' for r in missing)
                run_pip(f'install {names} -c "{constraints}"', f"{LABEL}: dependencies of {requirement.name}")
        if older:
            log(f"{LABEL}: keeping the WebUI's installed {', '.join(older)} for {requirement.name}.")
