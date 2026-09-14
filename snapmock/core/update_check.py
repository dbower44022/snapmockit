"""Check for Updates: the GitHub releases query of General UI PRD 3.8 (Help menu).

Decision 09-10-26 (Check for Updates kickoff decision 1, option A): the request
runs on the Qt event loop through ``QNetworkAccessManager`` from
``PyQt6.QtNetwork``, which ships inside the PyQt6 wheel; no thread and no new
dependency (Technical Architecture PRD 9.1). Decision 2, option A: the Help row
is the only trigger; nothing here runs at startup and nothing is remembered.

Everything but the request itself is pure and tested without the network:
the endpoint derived from ``REPOSITORY_URL``, the headers, the version parsing
and comparison, and :func:`interpret`, which turns a status code and a body into
an :class:`UpdateCheckResult`. :class:`UpdateChecker` sends the request and
hands the reply to :func:`interpret`; a test feeds it a canned reply through
:meth:`UpdateChecker.receive`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from snapmock import __version__
from snapmock.config.constants import APP_NAME, REPOSITORY_URL

GITHUB_API_URL = "https://api.github.com"
"""The GitHub REST API host; the endpoint below is built on it."""

TIMEOUT_MS = 10_000
"""The transfer timeout of one check (kickoff silence 1: ten seconds)."""

RATE_LIMITED_STATUSES = frozenset({403, 429})
"""GitHub answers a rate-limited request with one of these (kickoff silence 4)."""


def repository_path(repository_url: str = REPOSITORY_URL) -> str:
    """``owner/name`` from the repository page URL, so the path is never written twice."""
    return urlparse(repository_url).path.strip("/").removesuffix(".git")


def latest_release_url(repository_url: str = REPOSITORY_URL) -> str:
    """The ``releases/latest`` endpoint, which excludes drafts and pre-releases."""
    return f"{GITHUB_API_URL}/repos/{repository_path(repository_url)}/releases/latest"


def request_headers(version: str = __version__) -> dict[str, str]:
    """The two headers every check sends (kickoff silence 1)."""
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_NAME}/{version}",
    }


def parse_version(text: str) -> tuple[int, ...] | None:
    """``"v1.2.3"`` or ``"1.2.3"`` as ``(1, 2, 3)``; None when the text is not a version.

    A tag needs at least one dot-separated integer after the optional leading
    v; anything else (an empty tag, ``"latest"``, ``"1.2-beta"``) does not parse.
    """
    body = text.strip()
    if body[:1] in ("v", "V"):
        body = body[1:]
    if not body:
        return None
    parts = body.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


class Comparison(Enum):
    """How a release version stands against the running version."""

    NEWER = "newer"
    SAME = "same"
    OLDER = "older"


def compare(release: tuple[int, ...], running: tuple[int, ...]) -> Comparison:
    """Compare two parsed versions; missing trailing parts count as zero (1.2 equals 1.2.0)."""
    width = max(len(release), len(running))
    left = release + (0,) * (width - len(release))
    right = running + (0,) * (width - len(running))
    if left > right:
        return Comparison.NEWER
    if left < right:
        return Comparison.OLDER
    return Comparison.SAME


class Outcome(Enum):
    """The six things a check can report (the kickoff's outcome model)."""

    NEWER = "newer"
    UP_TO_DATE = "up_to_date"
    NO_RELEASE = "no_release"
    UNREADABLE = "unreadable"
    NETWORK_UNAVAILABLE = "network_unavailable"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class UpdateCheckResult:
    """What one check found.

    ``tag`` and ``release_url`` are filled for :attr:`Outcome.NEWER` and
    :attr:`Outcome.UP_TO_DATE`; ``release_url`` is the release page (``html_url``).
    """

    outcome: Outcome
    running_version: str = __version__
    tag: str = ""
    release_url: str = ""


def interpret(
    status: int | None, body: bytes, *, running_version: str = __version__
) -> UpdateCheckResult:
    """Turn a reply into a result. ``status`` None means no HTTP answer arrived.

    A failed or timed-out request, and a TLS failure, reach here with no status
    and are the network-unavailable outcome (kickoff decision 1). 404 is
    "no release published" (silence 3); 403 and 429 are rate limited (silence
    4); any other non-200 status, a body that is not JSON, or a tag that does
    not parse is "the release could not be read" (silence 2).
    """
    if status is None:
        return UpdateCheckResult(Outcome.NETWORK_UNAVAILABLE, running_version)
    if status == 404:
        return UpdateCheckResult(Outcome.NO_RELEASE, running_version)
    if status in RATE_LIMITED_STATUSES:
        return UpdateCheckResult(Outcome.RATE_LIMITED, running_version)
    if status != 200:
        return UpdateCheckResult(Outcome.UNREADABLE, running_version)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return UpdateCheckResult(Outcome.UNREADABLE, running_version)
    if not isinstance(data, dict):
        return UpdateCheckResult(Outcome.UNREADABLE, running_version)
    tag = str(data.get("tag_name") or "")
    release_url = str(data.get("html_url") or "")
    release = parse_version(tag)
    running = parse_version(running_version)
    if release is None or running is None:
        return UpdateCheckResult(Outcome.UNREADABLE, running_version, tag, release_url)
    if compare(release, running) is Comparison.NEWER:
        return UpdateCheckResult(Outcome.NEWER, running_version, tag, release_url)
    return UpdateCheckResult(Outcome.UP_TO_DATE, running_version, tag, release_url)


class UpdateChecker(QObject):
    """One check at a time: :meth:`start` sends the request, :attr:`finished` carries the result.

    The network access manager is created on the first :meth:`start`, so
    importing the module and building the window cost no network object. A
    test replaces :meth:`send` and calls :meth:`receive` with a canned reply.
    """

    finished = pyqtSignal(object)
    """Emitted once per check with the :class:`UpdateCheckResult`."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager: QNetworkAccessManager | None = None
        self._reply: QNetworkReply | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """True from :meth:`start` until the result is emitted."""
        return self._running

    def build_request(self) -> QNetworkRequest:
        """The request for the latest release, with the headers and the timeout."""
        request = QNetworkRequest(QUrl(latest_release_url()))
        for name, value in request_headers().items():
            request.setRawHeader(name.encode("ascii"), value.encode("ascii"))
        request.setTransferTimeout(TIMEOUT_MS)
        return request

    def start(self) -> None:
        """Send the request; nothing happens when a check is already running."""
        if self._running:
            return
        self._running = True
        self.send(self.build_request())

    def send(self, request: QNetworkRequest) -> None:
        """Put *request* on the network; the reply comes back through :meth:`_on_reply`."""
        if self._manager is None:
            self._manager = QNetworkAccessManager(self)
        reply = self._manager.get(request)
        if reply is None:  # pragma: no cover - Qt returns a reply object for every get
            self.receive(None, b"")
            return
        self._reply = reply
        reply.finished.connect(self._on_reply)

    def _on_reply(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:  # pragma: no cover - the slot fires once per reply
            return
        status_value = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status = int(status_value) if isinstance(status_value, int) else None
        body = reply.readAll().data()
        reply.deleteLater()
        self.receive(status, body)

    def receive(self, status: int | None, body: bytes) -> None:
        """Interpret a reply and emit :attr:`finished`; the check is over after this."""
        result = interpret(status, body)
        self._running = False
        self.finished.emit(result)
