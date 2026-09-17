"""Help > Check for Updates through the window (General UI PRD 3.8; notes Section 19).

Every check here is fed a canned reply through the checker's ``receive``; the
checker's ``send`` is replaced so nothing reaches the network.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QAbstractButton, QMenu, QMessageBox

from snapmock import __version__
from snapmock.config.constants import REPOSITORY_URL
from snapmock.core.update_check import Outcome, UpdateChecker, UpdateCheckResult
from snapmock.main_window import MainWindow


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """The checker records the request it would send instead of sending it."""
    sent: list[object] = []
    monkeypatch.setattr(UpdateChecker, "send", lambda _self, request: sent.append(request))
    return sent


@pytest.fixture()
def shown(monkeypatch: pytest.MonkeyPatch) -> list[QMessageBox]:
    """Every message box the window executes, closed at once through its Close button."""
    boxes: list[QMessageBox] = []

    def _exec(self: QMessageBox) -> int:
        boxes.append(self)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", _exec)
    return boxes


@pytest.fixture()
def opened(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The URLs handed to the desktop instead of opening a browser."""
    from snapmock import main_window as module

    urls: list[str] = []
    monkeypatch.setattr(
        module.QDesktopServices, "openUrl", staticmethod(lambda url: urls.append(url.toString()))
    )
    return urls


def _row(window: MainWindow) -> QAction:
    bar = window.menuBar()
    assert bar is not None
    for action in bar.actions():
        menu = action.menu()
        if isinstance(menu, QMenu) and action.text() == "&Help":
            for row in menu.actions():
                if row.text() == "Check for &Updates":
                    return row
    raise AssertionError("Check for Updates row not found")


def _hint(window: MainWindow) -> str:
    return window._status_bar._hint_label.text()  # noqa: SLF001


def _tool_hint(window: MainWindow) -> str:
    tool = window.tool_manager.active_tool
    assert tool is not None
    return tool.status_hint


def _labels(box: QMessageBox) -> set[str]:
    return {b.text().replace("&", "") for b in box.buttons()}


def _button(box: QMessageBox, label: str) -> QAbstractButton:
    for button in box.buttons():
        if button.text().replace("&", "") == label:
            return button
    raise AssertionError(label)


def _checker(window: MainWindow) -> UpdateChecker:
    return window._update_checker  # noqa: SLF001


def _release(tag: str, url: str = "https://github.com/x/y/releases/tag/v9") -> bytes:
    return json.dumps({"tag_name": tag, "html_url": url}).encode()


def test_the_row_starts_one_check_and_shows_the_hint(
    main_window: MainWindow, no_network: list[object], shown: list[QMessageBox]
) -> None:
    _row(main_window).trigger()
    assert len(no_network) == 1
    assert _checker(main_window).running
    assert _hint(main_window) == "Checking for updates…"
    _checker(main_window).receive(404, b"{}")
    assert not _checker(main_window).running
    assert len(shown) == 1
    assert _hint(main_window) == _tool_hint(main_window)


def test_a_second_click_while_running_explains_and_sends_nothing(
    main_window: MainWindow,
    no_network: list[object],
    unmet_messages: list[tuple[str, str]],
    shown: list[QMessageBox],
) -> None:
    _row(main_window).trigger()
    _row(main_window).trigger()
    assert len(no_network) == 1
    assert unmet_messages == [
        ("Check for Updates", "Check for Updates needs the running check to finish.")
    ]
    _checker(main_window).receive(404, b"{}")
    _row(main_window).trigger()
    assert len(no_network) == 2


def test_network_unavailable_is_the_section_1_3_message(
    main_window: MainWindow,
    unmet_messages: list[tuple[str, str]],
    shown: list[QMessageBox],
) -> None:
    _row(main_window).trigger()
    assert _hint(main_window) == "Checking for updates…"
    _checker(main_window).receive(None, b"")
    assert unmet_messages == [
        ("Check for Updates", "Check for Updates needs a network connection.")
    ]
    assert shown == []
    assert _hint(main_window) == _tool_hint(main_window)


def test_a_newer_release_offers_the_release_page(
    main_window: MainWindow, shown: list[QMessageBox], opened: list[str]
) -> None:
    _row(main_window).trigger()
    _checker(main_window).receive(200, _release("v9.0.0", "https://example.test/release"))
    assert len(shown) == 1
    box = shown[0]
    assert box.windowTitle() == "Check for Updates"
    assert box.icon() == QMessageBox.Icon.Information
    assert (
        box.text() == f"Snapmockit v9.0.0 is available. You are running Snapmockit {__version__}."
    )
    assert _labels(box) == {"Open Release Page", "Close"}
    _button(box, "Open Release Page").click()
    assert opened == ["https://example.test/release"]


def test_no_release_offers_the_repository_page(
    main_window: MainWindow, shown: list[QMessageBox], opened: list[str]
) -> None:
    _row(main_window).trigger()
    _checker(main_window).receive(404, b'{"message": "Not Found"}')
    box = shown[0]
    assert box.text() == (
        f"No release has been published yet. You are running Snapmockit {__version__}."
    )
    assert _labels(box) == {"Open Repository Page", "Close"}
    _button(box, "Open Repository Page").click()
    assert opened == [REPOSITORY_URL]


def test_up_to_date_rate_limited_and_unreadable_offer_close_only(
    main_window: MainWindow, shown: list[QMessageBox]
) -> None:
    _row(main_window).trigger()
    _checker(main_window).receive(200, _release(__version__))
    _row(main_window).trigger()
    _checker(main_window).receive(429, b"{}")
    _row(main_window).trigger()
    _checker(main_window).receive(200, b"<html>")
    _row(main_window).trigger()
    _checker(main_window).receive(200, _release("latest"))
    texts = [box.text() for box in shown]
    assert texts == [
        f"Snapmockit {__version__} is up to date. The latest release is {__version__}.",
        "GitHub declined the request; try again later.",
        "The latest release could not be read. Try again later.",
        "The latest release could not be read. Try again later.",
    ]
    for box in shown:
        assert _labels(box) == {"Close"}
        assert box.defaultButton() is _button(box, "Close")
        assert box.escapeButton() is _button(box, "Close")


def test_every_button_of_the_message_has_an_accessible_name(
    main_window: MainWindow, shown: list[QMessageBox]
) -> None:
    _row(main_window).trigger()
    _checker(main_window).receive(200, _release("v9.0.0"))
    for button in shown[0].findChildren(QAbstractButton):
        assert button.accessibleName(), button.text()


def test_message_text_for_every_outcome(main_window: MainWindow) -> None:
    text = main_window.update_message_text
    link = main_window.update_message_link
    newer = UpdateCheckResult(Outcome.NEWER, "0.1.0", "v0.2.0", "https://example.test/r")
    assert text(newer) == "Snapmockit v0.2.0 is available. You are running Snapmockit 0.1.0."
    assert link(newer) == ("Open Release Page", "https://example.test/r")
    assert link(UpdateCheckResult(Outcome.NEWER, "0.1.0", "v0.2.0", "")) is None
    assert link(UpdateCheckResult(Outcome.NO_RELEASE)) == ("Open Repository Page", REPOSITORY_URL)
    for outcome in (Outcome.UP_TO_DATE, Outcome.RATE_LIMITED, Outcome.UNREADABLE):
        assert link(UpdateCheckResult(outcome, "0.1.0", "v0.1.0", "u")) is None


def test_the_checker_belongs_to_the_window_and_the_request_is_the_endpoint(
    main_window: MainWindow, no_network: list[object]
) -> None:
    from snapmock.core.update_check import latest_release_url

    assert _checker(main_window).parent() is main_window
    _row(main_window).trigger()
    request = no_network[0]
    assert getattr(request, "url")().toString() == latest_release_url()
    assert QUrl(latest_release_url()).host() == "api.github.com"


def test_inside_a_flatpak_a_newer_release_names_the_bundle(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flatpak decision 5: the release page carries one file per form."""
    from snapmock import main_window as module

    monkeypatch.setattr(module, "in_flatpak", lambda: True)
    newer = UpdateCheckResult(Outcome.NEWER, "1.0.0", "v1.1.0", "https://example.test/r")
    text = main_window.update_message_text(newer)
    assert text.startswith("Snapmockit v1.1.0 is available. You are running Snapmockit 1.0.0.")
    assert text.endswith(
        "Download the new .flatpak bundle from the release page and install it with "
        "flatpak install."
    )
    # Only the newer outcome gains the instruction; the others read as they did.
    up_to_date = UpdateCheckResult(Outcome.UP_TO_DATE, "1.0.0", "v1.0.0", "https://example.test/r")
    assert main_window.update_message_text(up_to_date) == (
        "Snapmockit 1.0.0 is up to date. The latest release is v1.0.0."
    )
    assert main_window.update_message_link(newer) == (
        "Open Release Page",
        "https://example.test/r",
    )


def test_outside_a_flatpak_the_message_is_unchanged(
    main_window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    from snapmock import main_window as module

    monkeypatch.setattr(module, "in_flatpak", lambda: False)
    newer = UpdateCheckResult(Outcome.NEWER, "1.0.0", "v1.1.0", "https://example.test/r")
    assert main_window.update_message_text(newer) == (
        "Snapmockit v1.1.0 is available. You are running Snapmockit 1.0.0."
    )
