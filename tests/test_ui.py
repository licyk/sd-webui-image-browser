"""Keep the extension's tab down to the embedded browser."""

import sys
from html.parser import HTMLParser
from types import SimpleNamespace

from sd_webui_image_browser.host import on_ui_tabs


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


def test_tab_has_no_toolbar_and_hides_normal_status(monkeypatch):
    html = []

    class Blocks:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, "gradio", SimpleNamespace(Blocks=Blocks, HTML=html.append))
    tabs = on_ui_tabs()
    assert tabs[0][1:] == ("Hanaikada", "hanaikada")
    elements = Elements()
    elements.feed(html[0])
    assert not any(tag in {"button", "a", "details"} for tag, _ in elements.items)
    status = next(attrs for _, attrs in elements.items if attrs.get("class") == "hanaikada-status")
    assert "hidden" in status
    assert any(tag == "iframe" for tag, _ in elements.items)
