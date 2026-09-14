"""Help > About SnapMock (General UI PRD 11.6)."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.config.constants import APP_BUILD_DATE, APP_LICENSE, APP_VERSION
from snapmock.ui.about_dialog import AboutDialog, version_info_text


def test_about_shows_version_build_date_and_licence(qtbot: QtBot) -> None:
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    assert APP_VERSION in dlg.version_text
    assert APP_BUILD_DATE in dlg.version_text
    labels = [w.text() for w in dlg.findChildren(type(dlg._version_label))]  # noqa: SLF001
    assert any(APP_LICENSE in t for t in labels)
    assert any("Built with PyQt6" in t for t in labels)
    assert any("github.com/dbower44022/snapmockit/issues" in t for t in labels)


def test_copy_version_info_fills_the_clipboard(qtbot: QtBot) -> None:
    dlg = AboutDialog()
    qtbot.addWidget(dlg)
    dlg.copy_version_info()
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    text = clipboard.text()
    assert text == version_info_text()
    assert text.startswith(f"Snapmockit {APP_VERSION} (built {APP_BUILD_DATE})")
    assert "Qt " in text
