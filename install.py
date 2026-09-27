"""Install into the interpreter selected by the WebUI launcher."""

from pathlib import Path

from sd_webui_image_browser.installer import install_requirements

if __name__ == "__main__":
    import launch

    install_requirements(Path(__file__).with_name("requirements.txt"), launch.run_pip)
