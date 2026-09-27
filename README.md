# SD WebUI Image Browser

English | [简体中文](README_zh-CN.md)

An image browser for Stable Diffusion WebUI (A1111) and Forge / Forge Neo, powered by [Hanaikada](https://pypi.org/project/hanaikada/).

The extension embeds the native Hanaikada interface in the **Hanaikada** tab. It browses the WebUI's output folders in a virtualised grid, shows every generation parameter of an image, searches by prompt, model, LoRA, seed and more, tags images, compares two images, shows statistics, and moves, copies, renames and deletes files. These features are provided by Hanaikada.

## Installation

Requires Python 3.10 or newer.

### Option 1: Install through WebUI

1. Open **Extensions → Install from URL** in WebUI.
2. Enter `https://github.com/licyk/sd-webui-image-browser.git` and click **Install**.
3. Fully restart WebUI. Dependencies will be installed automatically, and the **Hanaikada** tab will become available.

### Option 2: Install from the command line

Open a terminal in the WebUI root directory (the directory containing the `extensions` folder) and run:

```bash
git clone https://github.com/licyk/sd-webui-image-browser.git extensions/sd-webui-image-browser
```

Start or fully restart WebUI after installation. Dependencies will be installed automatically, and the **Hanaikada** tab will become available.

### Dependencies

The installer never upgrades a package the WebUI already has. It installs Hanaikada without dependencies, then adds only the missing ones, resolved against the installed versions. The host's pins (A1111's `fastapi==0.94.0`, `Pillow==9.5.0`, `httpcore==0.15` and so on) stay as they are, and the launcher does not reinstall its requirements on every start. Later launches do nothing once the required Hanaikada version is installed.

A1111 pins FastAPI 0.94, which cannot read the `Annotated` parameters Hanaikada's API uses. While Hanaikada creates its routes, the extension rewrites those parameters into the older form. The patch applies only to Hanaikada's routes and is removed afterwards. Newer FastAPI versions (Forge Neo) are unaffected.

## Usage

1. Open the **Hanaikada** tab. It opens Browse at **All folders**, which shows the WebUI's output folders (txt2img, img2img, extras, grids, saved images and so on) side by side.
2. Images saved by the WebUI are indexed as soon as they are written and appear in an open folder right away. Images written by other programs are found by Hanaikada's folder watcher.
3. Use Search, Tags and Stats in the interface. The search is kept in the address inside the tab.

The tab shows the Hanaikada interface directly, without an extra toolbar or connection message. Error messages appear only when the connection fails, the login expires, or the frontend assets are missing.

Hanaikada has no "send to txt2img / img2img" feature; copy parameters from its information panel instead.

## Image folders

The extension reads the host's runtime settings instead of assuming the default `outputs` folder:

| Folder | Source |
| --- | --- |
| The WebUI data folder | `--data-dir`, with Hanaikada's `sd-webui` layout reading the WebUI's `config.json` |
| txt2img / img2img / extras | `outdir_samples`, or `outdir_txt2img_samples`, `outdir_img2img_samples`, `outdir_extras_samples` |
| Grids | `outdir_grids`, or `outdir_txt2img_grids`, `outdir_img2img_grids` |
| Saved images, init images | `outdir_save`, `outdir_init_images` |
| Forge Neo hires fix, videos | `outdir_hires_samples`, `outdir_videos` |

The layout lists only the output folders, their parent folders and their contents. Models, extensions and other folders of the installation are never listed or indexed. Relative paths are resolved from the WebUI's working directory, as the WebUI resolves them.

The output folders inside the data folder follow **Settings → Saving images/grids** without a restart, and a folder appears once the WebUI first saves into it. A folder the layout cannot reach gets its own entry in the root selector: a folder outside the data folder, Forge Neo's separate hires fix folder, or every output folder when `--ui-settings-file` moves `config.json` elsewhere. Fully restart WebUI after changing such a folder.

The folders are fixed by the WebUI and locked in Hanaikada: they cannot be added, changed or removed in its settings. Hanaikada reads and writes nothing outside them.

Extension data is stored in `data/` inside the extension directory: `settings.toml`, the index database `hanaikada.db`, the thumbnail cache and the tag backup. This directory is excluded by `.gitignore`. Hanaikada's own settings (thumbnail quality, watch interval, blur tags and so on) are changed in its Settings page; "All folders" is kept on.

## Settings and deployment

WebUI **Settings → Hanaikada** provides the external address for a reverse proxy, such as `https://example.com/webui/hanaikada`. It must include both the WebUI subpath and the extension path. Fully restart WebUI after changing it. Hanaikada checks the `Host` header while the WebUI listens on a loopback address; this setting adds the proxy's host name.

The service runs under `/hanaikada/` on WebUI's existing HTTP server; it does not start a second HTTP server. When WebUI uses a subpath, the browser URL is `<WebUI subpath>/hanaikada/`. Reverse proxies must forward both HTTP and WebSocket traffic under this path.

When Gradio login is enabled, the entire extension, including static pages, APIs, and WebSockets, validates the host session. Both Gradio 3 and 4 cookie formats are supported. No separate Hanaikada token is required. API-only mode uses HTTP Basic authentication from `--api-auth`. The regular graphical interface uses Gradio login; `--api-auth` does not replace authentication for the graphical interface.

The extension can move, rename and delete (to the trash) images in the output folders and is intended for trusted WebUI users. When WebUI listens on the network (`--listen`, `--share`), enable Gradio login.

## Development and validation

`scripts/image_browser_setup.py` registers WebUI callbacks, `sd_webui_image_browser/` adapts the host, and `javascript/hanaikada.js` handles the iframe. The extension does not modify host or Hanaikada source files.

After installing development dependencies, run these checks in an environment that can import Hanaikada:

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
node --check javascript/hanaikada.js
node --test tests/test_panel.mjs
```

Tests cover folder discovery for both hosts, both Gradio session formats, API-only authentication, mount subpaths, Socket.IO, the start-up scan, indexing of saved images, the FastAPI 0.94 shim, the installer, and lifecycle cleanup. They use temporary directories and small generated images.

The sub-application starts in WebUI's current event loop on the first authenticated request, and its scanner starts with it. Cleanup handles normal host shutdown, server event loop exit, and script unloading, including Forge's behavior of calling `on_app_started` after the server starts.

Optional browser checks require Playwright / Chromium and an installed Hanaikada release, which carries the built interface. The fixture uses real Gradio 3 or 4 and a temporary WebUI folder, and does not load Stable Diffusion:

```bash
python tests/browser_host.py --data-dir /tmp/image-browser-test
# Run in another terminal, then stop the fixture with Ctrl+C after checking:
node tests/browser_smoke.mjs
```

The fixture listens only on `127.0.0.1:17867`, with test credentials `smoke / smoke`. Use `PLAYWRIGHT_MODULE`, `CHROMIUM_PATH`, and `HANAIKADA_TEST_URL` to specify existing test tools and the target URL.

## License

This project is licensed under [GNU GPLv3](LICENSE).
