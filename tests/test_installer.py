from pathlib import Path

from sd_webui_image_browser import installer
from sd_webui_image_browser.package_analyzer import dependency_categorizer

INSTALLED = {"fastapi": "0.94.0", "pillow": "9.5.0", "websockets": "11.0.3", "h11": "0.12.0", "rich": "13.9.0"}
DEPENDENCIES = ["fastapi", "pillow>=10", "websockets>=12", "python-socketio", "send2trash", "tomli; python_version < '3.0'", "ruff; extra == 'dev'", "rich"]


def run(tmp_path, monkeypatch, installed, *, skip_install=False):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# comment\nhanaikada>=0.1.0\n\nnever-here; python_version < '3.0'\n")
    installed = dict(installed)
    calls, logs, constraints = [], [], []

    def run_pip(command, desc):
        calls.append(command)
        if "-c" in command:
            constraints.append(Path(command.rsplit('"', 2)[1]).read_text(encoding="utf-8").split())
        if "--no-deps" in command and not skip_install:
            installed["hanaikada"] = "0.1.0"

    monkeypatch.setattr(installer, "_installed", lambda name: installed.get(name.lower()))
    # The metadata's markers and optional groups go through the real analyzer.
    monkeypatch.setattr(dependency_categorizer, "requires", lambda name: DEPENDENCIES if name == "hanaikada" else None)
    monkeypatch.setattr(installer, "_pins", lambda exclude: [f"{n}=={v}" for n, v in installed.items() if n not in exclude])
    installer.install_requirements(requirements, run_pip, log=logs.append)
    return calls, logs, constraints


def test_adds_missing_dependencies_without_upgrading_the_host(tmp_path, monkeypatch):
    calls, logs, constraints = run(tmp_path, monkeypatch, INSTALLED)
    assert calls[0] == 'install --no-deps "hanaikada>=0.1.0"'
    assert calls[1].startswith('install "python-socketio" "send2trash" -c "')
    assert len(calls) == 2
    # New packages resolve against what is installed, so e.g. h11 stays where httpcore needs it.
    assert "h11==0.12.0" in constraints[0] and "pillow==9.5.0" in constraints[0]
    assert not any(pin.startswith(("hanaikada==", "python-socketio==")) for pin in constraints[0])
    assert logs == ["SD WebUI Image Browser: keeping the WebUI's installed pillow 9.5.0 (>=10), websockets 11.0.3 (>=12) for hanaikada."]


def test_satisfied_requirement_does_nothing(tmp_path, monkeypatch):
    assert run(tmp_path, monkeypatch, {**INSTALLED, "hanaikada": "0.1.3"}) == ([], [], [])


def test_outdated_package_is_upgraded_and_complete_dependencies_need_no_pip(tmp_path, monkeypatch):
    complete = {**INSTALLED, "hanaikada": "0.0.9", "pillow": "12.0", "websockets": "15.0", "python-socketio": "5.0", "send2trash": "1.8"}
    assert run(tmp_path, monkeypatch, complete) == (['install --no-deps "hanaikada>=0.1.0"'], [], [])


def test_skip_install_stops_quietly(tmp_path, monkeypatch):
    calls, logs, _ = run(tmp_path, monkeypatch, INSTALLED, skip_install=True)
    assert calls == ['install --no-deps "hanaikada>=0.1.0"'] and logs == []
