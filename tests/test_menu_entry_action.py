"""The Help menu's Add to Menu / Remove from Menu, and the offer on the first start.

Menu-entry Phase 2, through the window on the offscreen platform with the writing
module stubbed: nothing here writes a desktop entry, an icon, or a MIME file, and
nothing reads the developer's own ``~/.local/share``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtWidgets import QMenu, QMessageBox
from pytest import MonkeyPatch

from snapmock.config import desktop_entry
from snapmock.config.constants import APP_NAME
from snapmock.main_window import MainWindow


class FakeEntry:
    """A stand-in for ``config.desktop_entry``: it records instead of writing."""

    def __init__(self, installed: bool = False, reason: str | None = None) -> None:
        self._installed = installed
        self.reason = reason
        self.installs: list[str | None] = []
        self.removals = 0
        self.copies: list[tuple[Path, Path]] = []
        self.running: Path | None = None
        self.destination = Path("/home/nobody/Applications/Snapmockit.AppImage")
        self.outcome = desktop_entry.Outcome(action=f"{APP_NAME} is in the menu.", paths=(Path(),))
        self.copy_error: Exception | None = None

    def installed(self) -> bool:
        return self._installed

    def unsupported_reason(self) -> str | None:
        return self.reason

    def install(self, program: str | None = None, **_: Any) -> desktop_entry.Outcome:
        self.installs.append(program)
        self._installed = True
        return self.outcome

    def remove(self, **_: Any) -> desktop_entry.Outcome:
        self.removals += 1
        self._installed = False
        return desktop_entry.Outcome(
            action=f"{APP_NAME} is no longer in the menu.", paths=(Path(),)
        )

    def running_appimage(self, **_: Any) -> Path | None:
        return self.running

    def appimage_destination(self, **_: Any) -> Path:
        return self.destination

    def copy_appimage(self, source: Path, destination: Path) -> Path:
        if self.copy_error is not None:
            raise self.copy_error
        self.copies.append((source, destination))
        return destination


@pytest.fixture
def entry(monkeypatch: MonkeyPatch) -> FakeEntry:
    """Replace the writing module the window calls, for the whole test."""
    fake = FakeEntry()
    monkeypatch.setattr("snapmock.main_window.desktop_entry", fake)
    return fake


@pytest.fixture
def shown(qtbot: Any) -> list[tuple[str, str]]:
    """Every message box the action opens, answered at once with its default."""
    return []


def answer_boxes(monkeypatch: MonkeyPatch, shown: list[tuple[str, str]], button: str = "") -> None:
    """Record each message the action shows; click *button* on the question box."""

    def information(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> Any:
        shown.append((title, text))
        return QMessageBox.StandardButton.Ok

    def question(parent: Any, title: str, text: str, *args: Any, **kwargs: Any) -> Any:
        shown.append((title, text))
        return QMessageBox.StandardButton.Yes if button == "yes" else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "information", staticmethod(information))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))

    def exec_box(self: QMessageBox) -> int:
        shown.append((self.windowTitle(), self.text()))
        for candidate in self.buttons():
            if candidate.text().replace("&", "") == button:
                self._clicked = candidate  # type: ignore[attr-defined]
                return 0
        self._clicked = self.defaultButton()  # type: ignore[attr-defined]
        return 0

    def clicked_button(self: QMessageBox) -> Any:
        return getattr(self, "_clicked", self.defaultButton())

    monkeypatch.setattr(QMessageBox, "exec", exec_box)
    monkeypatch.setattr(QMessageBox, "clickedButton", clicked_button)


def help_menu(window: MainWindow) -> QMenu:
    """The Help menu of the window's menu bar."""
    bar = window.menuBar()
    assert bar is not None
    for action in bar.actions():
        menu = action.menu()
        if menu is not None and action.text().replace("&", "") == "Help":
            return menu
    raise AssertionError("no Help menu")


def menu_row(window: MainWindow) -> Any:
    """The Add to Menu / Remove from Menu row, whatever it currently reads."""
    for action in help_menu(window).actions():
        text = action.text().replace("&", "")
        if text.endswith("from Menu") or text.endswith("to Menu"):
            return action
    raise AssertionError("no menu-entry row")


# ---- the row and its label -------------------------------------------------------------


def test_the_row_sits_after_report_a_bug_and_before_the_separator(
    qtbot: Any, entry: FakeEntry
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    texts = [
        a.text().replace("&", "") if not a.isSeparator() else "---"
        for a in help_menu(window).actions()
    ]
    assert texts[:6] == [
        "Welcome / Getting Started",
        "Documentation",
        "Keyboard Shortcuts",
        "Report a Bug",
        "Add to Menu",
        "---",
    ]


def test_the_label_follows_the_entry_when_the_menu_opens(qtbot: Any, entry: FakeEntry) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    assert menu_row(window).text().replace("&", "") == "Add to Menu"

    entry._installed = True
    help_menu(window).aboutToShow.emit()
    assert menu_row(window).text().replace("&", "") == "Remove from Menu"


def test_a_form_that_needs_nothing_says_so_and_writes_nothing(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    """No control is disabled (General UI PRD 1.3): the Flatpak's row explains itself."""
    entry.reason = "This Flatpak installation is already in the menu."
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages)

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert messages and "already in the menu" in messages[0][1]
    assert entry.installs == []
    assert entry.removals == 0


# ---- adding and removing ---------------------------------------------------------------


def test_adding_writes_and_reports_the_icon_rescan(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages)

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.installs == [None]
    assert messages[-1][0] == "Add to Menu"
    assert "is in the menu" in messages[-1][1]
    assert MainWindow.ICON_RESCAN_NOTE in messages[-1][1]
    assert menu_row(window).text().replace("&", "") == "Remove from Menu"


def test_a_failed_install_is_reported_without_the_rescan_note(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    entry.outcome = desktop_entry.Outcome(
        action=f"{APP_NAME} could not be added to the menu.",
        notes=("/nowhere could not be written (Permission denied).",),
    )
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages)

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert "could not be added" in messages[-1][1]
    assert MainWindow.ICON_RESCAN_NOTE not in messages[-1][1]


def test_removing_deletes_and_reports(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    entry._installed = True
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages)

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.removals == 1
    assert "no longer in the menu" in messages[-1][1]
    assert menu_row(window).text().replace("&", "") == "Add to Menu"


# ---- the AppImage's question (decision 3) ----------------------------------------------


def test_the_appimage_offers_the_copy_and_points_the_entry_at_it(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    running = tmp_path / "Downloads" / "Snapmockit-1.2.0-x86_64.AppImage"
    running.parent.mkdir(parents=True)
    running.write_bytes(b"\x00" * 2048)
    entry.running = running
    entry.destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages, button="Copy and Add")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.copies == [(running, entry.destination)]
    assert entry.installs == [str(entry.destination)]
    assert str(entry.destination) in messages[0][1]


def test_the_appimage_can_be_added_where_it_sits(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    running = tmp_path / "Snapmockit-1.2.0-x86_64.AppImage"
    running.write_bytes(b"\x00" * 2048)
    entry.running = running
    entry.destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    answer_boxes(monkeypatch, [], button="Add Without Copying")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.copies == []
    assert entry.installs == [str(running)]


def test_cancelling_the_question_writes_nothing(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    running = tmp_path / "Snapmockit.AppImage"
    running.write_bytes(b"\x00")
    entry.running = running
    entry.destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    answer_boxes(monkeypatch, [], button="Cancel")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.installs == []
    assert entry.copies == []


def test_an_appimage_already_at_the_fixed_name_is_asked_nothing(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"\x00")
    entry.running = destination
    entry.destination = destination
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages)

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.installs == [None]
    assert len(messages) == 1  # the outcome alone; no question was asked


def test_a_copy_that_fails_is_reported_and_nothing_is_written(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    running = tmp_path / "Snapmockit.AppImage"
    running.write_bytes(b"\x00")
    entry.running = running
    entry.destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    entry.copy_error = ValueError("that is not an AppImage")
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages, button="Copy and Add")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert entry.installs == []
    assert "could not be written" in messages[-1][1]


def test_removing_offers_to_delete_the_copy_and_leaves_it_on_no(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"\x00" * 4096)
    entry.destination = destination
    entry.running = tmp_path / "Downloads" / f"{APP_NAME}-1.2.0-x86_64.AppImage"
    entry._installed = True
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages, button="")  # the question answers No

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert destination.is_file()
    assert any("Delete it as well?" in text for _, text in messages)


def test_removing_deletes_the_copy_on_yes(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"\x00" * 4096)
    entry.destination = destination
    entry.running = tmp_path / "Downloads" / f"{APP_NAME}-1.2.0-x86_64.AppImage"
    entry._installed = True
    answer_boxes(monkeypatch, [], button="yes")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert not destination.exists()


def test_the_running_appimage_is_named_as_left_in_place_not_offered(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Deleting a mounted AppImage takes the running application's own files away."""
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"\x00")
    entry.destination = destination
    entry.running = destination
    entry._installed = True
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages, button="yes")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert destination.is_file()
    assert not any("Delete it as well?" in text for _, text in messages)
    assert any("is the file you are running" in text for _, text in messages)


def test_another_form_is_never_offered_the_appimage_copy(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """A copy at that path under an installation from the index is the user's own."""
    destination = tmp_path / "Applications" / f"{APP_NAME}.AppImage"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"\x00" * 4096)
    entry.destination = destination
    entry.running = None
    entry._installed = True
    messages: list[tuple[str, str]] = []
    answer_boxes(monkeypatch, messages, button="yes")

    window = MainWindow()
    qtbot.addWidget(window)
    menu_row(window).trigger()

    assert destination.is_file()
    assert len(messages) == 1  # the removal alone


# ---- the offer on the first start (decision 1) -----------------------------------------


def toast_calls(window: MainWindow, monkeypatch: MonkeyPatch) -> list[tuple[str, str, Any]]:
    """Record what the window puts in its toast instead of showing one."""
    calls: list[tuple[str, str, Any]] = []

    def show_message(text: str, link_text: str = "", on_click: Any = None) -> None:
        calls.append((text, link_text, on_click))

    monkeypatch.setattr(window._toast, "show_message", show_message)
    return calls


def test_the_offer_is_a_toast_with_the_action_on_it(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.set_desktop_entry_offer_shown(False)
    calls = toast_calls(window, monkeypatch)

    window.offer_desktop_entry_once()

    assert len(calls) == 1
    text, link_text, on_click = calls[0]
    assert "not in your desktop's menu" in text
    assert link_text == "Add to Menu"
    assert on_click is not None
    assert window._settings.desktop_entry_offer_shown()


def test_the_offer_is_made_once(qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.set_desktop_entry_offer_shown(False)
    calls = toast_calls(window, monkeypatch)

    window.offer_desktop_entry_once()
    window.offer_desktop_entry_once()

    assert len(calls) == 1


def test_no_offer_where_the_entry_exists_or_the_form_needs_nothing(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.set_desktop_entry_offer_shown(False)
    calls = toast_calls(window, monkeypatch)

    entry._installed = True
    window.offer_desktop_entry_once()
    assert calls == []
    assert not window._settings.desktop_entry_offer_shown()

    entry._installed = False
    entry.reason = "This Flatpak installation is already in the menu."
    window.offer_desktop_entry_once()
    assert calls == []
    assert not window._settings.desktop_entry_offer_shown()


def test_the_offer_installs_when_it_is_clicked(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    answer_boxes(monkeypatch, [])
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.set_desktop_entry_offer_shown(False)
    calls = toast_calls(window, monkeypatch)

    window.offer_desktop_entry_once()
    calls[0][2]()

    assert entry.installs == [None]


def test_a_start_that_owes_a_message_defers_the_offer(
    qtbot: Any, entry: FakeEntry, monkeypatch: MonkeyPatch
) -> None:
    """The startup message and the offer share one toast, so they never collide."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.set_desktop_entry_offer_shown(False)
    window.show_startup_message("Your settings were moved.")
    calls = toast_calls(window, monkeypatch)

    window.offer_desktop_entry_once()

    assert calls == []
    assert not window._settings.desktop_entry_offer_shown()
