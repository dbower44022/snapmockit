"""AboutDialog — version, build date, licence, links, credits, Copy Version Info (PRD 11.6)."""

from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import QT_VERSION_STR, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from snapmock.config.constants import (
    APP_BUILD_DATE,
    APP_LICENSE,
    APP_NAME,
    APP_VERSION,
    COPYRIGHT,
    DOCUMENTATION_URL,
    ISSUES_URL,
    REPOSITORY_URL,
)
from snapmock.ui.accessibility import apply_default_names
from snapmock.ui.icons import render_application_icon

TAGLINE = "Screenshot Annotation & UI Mockup Tool"
CREDITS = ["Doug Bower", "Tabler Icons by Paweł Kuna (MIT)"]


def pyqt_version() -> str:
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR
    except ImportError:  # pragma: no cover - always present with PyQt6
        return "unknown"
    return PYQT_VERSION_STR


def version_info_text() -> str:
    """The plain-text block Copy Version Info puts on the clipboard, for bug reports."""
    return "\n".join(
        [
            f"{APP_NAME} {APP_VERSION} (built {APP_BUILD_DATE})",
            f"Python {platform.python_version()}",
            f"PyQt {pyqt_version()} / Qt {QT_VERSION_STR}",
            f"{platform.system()} {platform.release()} ({platform.machine()})",
            f"Executable: {sys.executable}",
        ]
    )


class AboutDialog(QDialog):
    """Help > About SnapMock."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(render_application_icon(48))
        header.addWidget(icon)
        title = QLabel(f"<h2 style='margin:0'>{APP_NAME}</h2><p style='margin:0'>{TAGLINE}</p>")
        header.addWidget(title, 1)
        layout.addLayout(header)

        self._version_label = QLabel(f"Version {APP_VERSION} · built {APP_BUILD_DATE}")
        layout.addWidget(self._version_label)

        licence = QLabel(f"{APP_LICENSE}. {COPYRIGHT}.")
        licence.setWordWrap(True)
        layout.addWidget(licence)

        layout.addWidget(QLabel(f"Built with PyQt6 {pyqt_version()} and Qt {QT_VERSION_STR}."))

        links = QLabel(
            f'<a href="{DOCUMENTATION_URL}">Project website</a> · '
            f'<a href="{REPOSITORY_URL}">GitHub repository</a> · '
            f'<a href="{ISSUES_URL}">Issue tracker</a>'
        )
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        layout.addWidget(links)

        credits = QLabel("Credits: " + ", ".join(CREDITS))
        credits.setWordWrap(True)
        layout.addWidget(credits)

        buttons = QDialogButtonBox()
        self._copy_button = QPushButton("Copy Version Info")
        self._copy_button.clicked.connect(self.copy_version_info)
        buttons.addButton(self._copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        close = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.setDefault(True)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        apply_default_names(self)

    def copy_version_info(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(version_info_text())
        self._copy_button.setText("Copied")

    @property
    def version_text(self) -> str:
        return self._version_label.text()
