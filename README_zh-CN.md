# SD WebUI Image Browser

[English](README.md) | 简体中文

适用于 Stable Diffusion WebUI（A1111）和 Forge / Forge Neo 的图片浏览扩展，由 [Hanaikada](https://pypi.org/project/hanaikada/) 提供支持。

扩展在 **Hanaikada** 标签页中嵌入 Hanaikada 原生界面：以虚拟化网格浏览 WebUI 的输出文件夹，查看图片的全部生成参数，按提示词、模型、LoRA、种子等搜索，为图片打标签，对比两张图片，查看统计，并移动、复制、重命名和删除文件。这些功能均由 Hanaikada 提供。

## 安装

需要 Python 3.10 或更高版本。

### 方式一：通过 WebUI 安装

1. 在 WebUI 中打开 **扩展 → 从网址安装**。
2. 输入 `https://github.com/licyk/sd-webui-image-browser.git`，点击 **安装**。
3. 完全重启 WebUI。依赖会自动安装，之后即可使用 **Hanaikada** 标签页。

### 方式二：通过命令行安装

在 WebUI 根目录（包含 `extensions` 文件夹的目录）中打开终端并运行：

```bash
git clone https://github.com/licyk/sd-webui-image-browser.git extensions/sd-webui-image-browser
```

安装后启动或完全重启 WebUI。依赖会自动安装，之后即可使用 **Hanaikada** 标签页。

### 依赖

安装程序不会升级 WebUI 已安装的任何包：先不带依赖安装 Hanaikada，再只补装缺少的依赖，并按已安装的版本解析。宿主固定的版本（A1111 的 `fastapi==0.94.0`、`Pillow==9.5.0`、`httpcore==0.15` 等）保持不变，启动器也不会因此在每次启动时重装依赖。已安装所需版本的 Hanaikada 后，之后的启动不会再做任何操作。

A1111 固定的 FastAPI 0.94 无法识别 Hanaikada API 使用的 `Annotated` 参数。扩展会在 Hanaikada 创建路由期间把这些参数改写为旧写法；该补丁只作用于 Hanaikada 的路由，完成后即撤销。较新的 FastAPI（Forge Neo）不受影响。

## 使用

1. 打开 **Hanaikada** 标签页。默认进入“浏览”的 **全部文件夹**，并列显示 WebUI 的各个输出文件夹（txt2img、img2img、extras、网格图、保存的图片等）。
2. WebUI 保存的图片在写入后立即加入索引，并立刻出现在已打开的文件夹中；其他程序写入的图片由 Hanaikada 的文件夹监视发现。
3. 在界面中使用搜索、标签和统计。搜索条件保存在标签页内的地址中。

标签页直接显示 Hanaikada 界面，没有额外的工具栏或连接提示。仅在连接失败、登录失效或缺少前端资源时显示错误信息。

**发送到文生图 / 图生图 / 局部重绘 / 后期处理**（图片菜单或查看器的“发送到”按钮）与 WebUI 自带的“发送到”按钮一致：WebUI 会用图片参数填写各个字段、设置图片及尺寸，并切换到对应标签页。WebUI 图片按原样发送自己的参数；ComfyUI 或 InvokeAI 图片发送根据元数据重建的参数；没有参数的图片只发送图片本身，不会误粘贴上一次生成的参数。发送到文生图需要图片带有参数；后期处理只接收图片。此功能需要 Hanaikada 0.1.3 或更高版本；版本较旧时不会出现这些选项。

## 图片文件夹

扩展读取宿主的运行时设置，而不是假定使用默认的 `outputs` 文件夹：

| 文件夹 | 来源 |
| --- | --- |
| WebUI 数据目录 | `--data-dir`，由 Hanaikada 的 `sd-webui` 布局读取 WebUI 的 `config.json` |
| txt2img / img2img / extras | `outdir_samples`，或 `outdir_txt2img_samples`、`outdir_img2img_samples`、`outdir_extras_samples` |
| 网格图 | `outdir_grids`，或 `outdir_txt2img_grids`、`outdir_img2img_grids` |
| 保存的图片、初始图片 | `outdir_save`、`outdir_init_images` |
| Forge Neo 高分辨率修复、视频 | `outdir_hires_samples`、`outdir_videos` |

布局只列出输出文件夹、它们的上级文件夹和其中的内容，安装目录中的模型、扩展等文件夹不会被列出或索引。相对路径按 WebUI 的工作目录解析，与 WebUI 自身一致。

数据目录内的输出文件夹无需重启即可跟随 **设置 → 保存图像/网格图** 的修改，文件夹会在 WebUI 首次向其保存图片后出现。布局无法覆盖的文件夹会在根目录选择器中单独列出：位于数据目录之外的文件夹、Forge Neo 单独设置的高分辨率修复文件夹，以及 `--ui-settings-file` 把 `config.json` 放在别处时的全部输出文件夹。修改这类文件夹后请完全重启 WebUI。

这些文件夹由 WebUI 决定，并在 Hanaikada 中锁定：无法在其设置中添加、修改或移除。Hanaikada 不会读写它们之外的任何内容。

扩展数据保存在扩展目录内的 `data/` 中，包括 `settings.toml`、索引数据库 `hanaikada.db`、缩略图缓存和标签备份。该目录已被 `.gitignore` 排除。Hanaikada 自身的设置（缩略图质量、监视间隔、模糊标签等）在其设置页中修改；“全部文件夹”始终开启。

## 设置与部署

WebUI **设置 → Hanaikada** 提供反向代理外部地址，例如 `https://example.com/webui/hanaikada`，必须同时包含 WebUI 子路径和扩展路径。修改后请完全重启 WebUI。WebUI 监听回环地址时，Hanaikada 会检查 `Host` 请求头；此设置用于放行代理的主机名。

服务运行在 WebUI 现有 HTTP 服务器的 `/hanaikada/` 下，不会另外启动 HTTP 服务器。WebUI 使用子路径时，浏览器地址为 `<WebUI 子路径>/hanaikada/`。反向代理需要同时转发该路径下的 HTTP 和 WebSocket 流量。

启用 Gradio 登录后，扩展的全部内容（包括静态页面、API 和 WebSocket）都会校验宿主会话，同时支持 Gradio 3 和 4 的 Cookie 格式，无需单独的 Hanaikada 令牌。仅 API 模式使用 `--api-auth` 的 HTTP Basic 认证。常规图形界面使用 Gradio 登录；`--api-auth` 不能替代图形界面的认证。

扩展可以移动、重命名和删除（移至回收站）输出文件夹中的图片，适用于可信的 WebUI 用户。WebUI 在网络上监听（`--listen`、`--share`）时，请启用 Gradio 登录。

## 开发与验证

`scripts/image_browser_setup.py` 注册 WebUI 回调，`sd_webui_image_browser/` 适配宿主，`javascript/hanaikada.js` 负责 iframe。扩展不会修改宿主或 Hanaikada 的源文件。

安装开发依赖后，在可以导入 Hanaikada 的环境中运行以下检查：

```bash
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
node --check javascript/hanaikada.js
node --test tests/test_panel.mjs
```

测试覆盖两种宿主的文件夹识别、两种 Gradio 会话格式、仅 API 认证、挂载子路径、Socket.IO、启动扫描、保存图片的即时索引、FastAPI 0.94 兼容补丁、安装程序以及生命周期清理，均使用临时目录和生成的小图片。

子应用在第一个通过认证的请求到达时于 WebUI 当前事件循环中启动，扫描器随之启动。清理逻辑覆盖宿主正常关闭、服务器事件循环退出和脚本卸载，包括 Forge 在服务器启动后才调用 `on_app_started` 的行为。

可选的浏览器检查需要 Playwright / Chromium 和已安装的 Hanaikada 发行版（其中包含构建好的界面）。测试夹具使用真实的 Gradio 3 或 4 和临时 WebUI 目录，不加载 Stable Diffusion：

```bash
python tests/browser_host.py --data-dir /tmp/image-browser-test
# 在另一个终端运行，检查完成后按 Ctrl+C 停止夹具：
node tests/browser_smoke.mjs
```

夹具仅监听 `127.0.0.1:17867`，测试账号为 `smoke / smoke`。可用 `PLAYWRIGHT_MODULE`、`CHROMIUM_PATH` 和 `HANAIKADA_TEST_URL` 指定已有的测试工具和目标地址。

## 许可证

本项目基于 [GNU GPLv3](LICENSE) 许可证发布。
