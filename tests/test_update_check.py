"""The Check for Updates module (General UI PRD 3.8; implementation notes Section 19).

No test here reaches the network: the pure functions take strings and bytes,
and the checker's ``send`` is replaced before ``start`` so ``receive`` can be
fed a canned reply.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QObject
from PyQt6.QtNetwork import QNetworkRequest
from pytestqt.qtbot import QtBot

from snapmock import __version__
from snapmock.config.constants import APP_VERSION, REPOSITORY_URL
from snapmock.core.update_check import (
    TIMEOUT_MS,
    Comparison,
    Outcome,
    UpdateChecker,
    UpdateCheckResult,
    compare,
    interpret,
    latest_release_url,
    parse_version,
    repository_path,
    request_headers,
)


def release_body(tag: str, url: str = "https://github.com/x/y/releases/tag/t") -> bytes:
    return json.dumps({"tag_name": tag, "html_url": url}).encode()


# ---- the endpoint and headers (silence 1) ----


def test_repository_path_is_derived_from_the_repository_url() -> None:
    assert repository_path() == "dbower44022/Snagit_FOSS"
    assert repository_path("https://github.com/o/n.git") == "o/n"
    assert repository_path("https://github.com/o/n/") == "o/n"


def test_latest_release_endpoint_excludes_drafts_and_pre_releases() -> None:
    assert latest_release_url() == (
        "https://api.github.com/repos/dbower44022/Snagit_FOSS/releases/latest"
    )
    assert REPOSITORY_URL.endswith(repository_path())


def test_headers_name_the_api_version_and_the_application() -> None:
    headers = request_headers()
    assert headers == {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Snapmockit/{__version__}",
    }
    assert __version__ == APP_VERSION


# ---- versions (silence 2) ----


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        ("V0.1.0", (0, 1, 0)),
        (" v2.0 ", (2, 0)),
        ("7", (7,)),
        ("", None),
        ("v", None),
        ("latest", None),
        ("1.2-beta", None),
        ("1..2", None),
        ("1.2.3rc1", None),
    ],
)
def test_parse_version(text: str, expected: tuple[int, ...] | None) -> None:
    assert parse_version(text) == expected


def test_compare_pads_missing_parts_with_zero() -> None:
    assert compare((0, 2, 0), (0, 1, 0)) is Comparison.NEWER
    assert compare((0, 1, 0), (0, 1, 0)) is Comparison.SAME
    assert compare((0, 1), (0, 1, 0)) is Comparison.SAME
    assert compare((0, 1, 0, 1), (0, 1)) is Comparison.NEWER
    assert compare((0, 0, 9), (0, 1, 0)) is Comparison.OLDER
    assert compare((1,), (0, 9, 9)) is Comparison.NEWER


# ---- the outcome model ----


def test_no_status_is_network_unavailable() -> None:
    result = interpret(None, b"")
    assert result == UpdateCheckResult(Outcome.NETWORK_UNAVAILABLE, __version__)


def test_404_is_no_release_published() -> None:
    assert interpret(404, b'{"message":"Not Found"}').outcome is Outcome.NO_RELEASE


@pytest.mark.parametrize("status", [403, 429])
def test_403_and_429_are_rate_limited(status: int) -> None:
    assert interpret(status, b"{}").outcome is Outcome.RATE_LIMITED


@pytest.mark.parametrize("status", [500, 301, 200])
def test_other_statuses_and_bad_bodies_are_unreadable(status: int) -> None:
    body = b"<html>" if status == 200 else release_body("v9.0.0")
    assert interpret(status, body).outcome is Outcome.UNREADABLE


def test_a_json_list_is_unreadable() -> None:
    assert interpret(200, b"[1, 2]").outcome is Outcome.UNREADABLE


def test_a_tag_that_does_not_parse_is_unreadable_but_keeps_the_tag() -> None:
    result = interpret(200, release_body("latest", "https://example.test/r"))
    assert result.outcome is Outcome.UNREADABLE
    assert result.tag == "latest"
    assert result.release_url == "https://example.test/r"


def test_a_newer_release_carries_the_tag_and_the_release_page() -> None:
    result = interpret(
        200, release_body("v0.2.0", "https://example.test/r"), running_version="0.1.0"
    )
    assert result == UpdateCheckResult(Outcome.NEWER, "0.1.0", "v0.2.0", "https://example.test/r")


@pytest.mark.parametrize("tag", ["v0.1.0", "0.1.0", "0.1", "v0.0.9"])
def test_the_same_or_an_older_release_is_up_to_date(tag: str) -> None:
    result = interpret(200, release_body(tag), running_version="0.1.0")
    assert result.outcome is Outcome.UP_TO_DATE
    assert result.tag == tag


def test_the_running_version_defaults_to_the_package_version() -> None:
    assert interpret(404, b"").running_version == __version__


# ---- the checker ----


class _Sent:
    """Records the request the checker would have put on the network."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.requests: list[QNetworkRequest] = []
        monkeypatch.setattr(
            UpdateChecker, "send", lambda _self, request: self.requests.append(request)
        )


def test_start_sends_one_request_with_the_headers_and_timeout(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _Sent(monkeypatch)
    checker = UpdateChecker()
    assert not checker.running
    checker.start()
    assert checker.running
    assert len(sent.requests) == 1
    request = sent.requests[0]
    assert request.url().toString() == latest_release_url()
    assert request.rawHeader(b"Accept").data() == b"application/vnd.github+json"
    assert request.rawHeader(b"User-Agent").data() == f"Snapmockit/{__version__}".encode()
    assert request.transferTimeout() == TIMEOUT_MS


def test_a_second_start_while_running_sends_nothing(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _Sent(monkeypatch)
    checker = UpdateChecker()
    checker.start()
    checker.start()
    assert len(sent.requests) == 1


def test_receive_emits_the_result_and_ends_the_check(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    _Sent(monkeypatch)
    checker = UpdateChecker()
    results: list[UpdateCheckResult] = []
    checker.finished.connect(results.append)
    checker.start()
    checker.receive(200, release_body("v1.0.0", "https://example.test/r"))
    assert not checker.running
    assert results == [
        UpdateCheckResult(Outcome.NEWER, __version__, "v1.0.0", "https://example.test/r")
    ]
    checker.start()
    checker.receive(None, b"")
    assert results[-1].outcome is Outcome.NETWORK_UNAVAILABLE


def test_the_checker_is_a_child_of_its_parent(qtbot: QtBot) -> None:
    parent = QObject()
    checker = UpdateChecker(parent)
    assert checker.parent() is parent
