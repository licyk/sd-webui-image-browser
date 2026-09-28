"""Logger settings read by the vendored package analyzer."""

import logging
import os

LOGGER_NAME = os.getenv("SD_WEBUI_IMAGE_BROWSER_LOGGER_NAME", "Image-Browser")
LOGGER_LEVEL = int(os.getenv("SD_WEBUI_IMAGE_BROWSER_LOGGER_LEVEL", str(logging.INFO)))
LOGGER_COLOR = os.getenv("SD_WEBUI_IMAGE_BROWSER_LOGGER_COLOR", "1").lower() not in {"0", "false", "none"}
