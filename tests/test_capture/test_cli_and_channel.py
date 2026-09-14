"""Tests for command-line parsing and the single-instance channel (PRD 3.5)."""

from __future__ import annotations

import socket
import tempfile
import uuid
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from snapmock.capture.cli import parse_capture_args, parse_command_line
from snapmock.capture.single_instance import SingleInstanceChannel, try_forward


def test_parse_capture_args_forms() -> None:
    assert parse_capture_args(["snapmock"]) is None
    cmd = parse_capture_args(["snapmock", "--capture"])
    assert cmd is not None and cmd.mode is None and cmd.delay_seconds is None
    cmd = parse_capture_args(["snapmock", "--capture", "region", "--delay", "3"])
    assert cmd is not None and cmd.mode == "region" and cmd.delay_seconds == 3
    cmd = parse_capture_args(["--capture=full", "--delay=99"])
    assert cmd is not None and cmd.mode == "full" and cmd.delay_seconds == 60
    cmd = parse_capture_args(["--capture", "--delay", "x"])
    assert cmd is not None and cmd.mode is None and cmd.delay_seconds is None


def test_forward_without_instance_returns_false(qapp: QApplication) -> None:
    assert try_forward(["--capture"], name=f"snapmock-test-none-{uuid.uuid4().hex}") is False


def test_channel_receives_forwarded_command(qtbot: QtBot) -> None:
    name = f"snapmock-test-{uuid.uuid4().hex}"
    channel = SingleInstanceChannel(name)
    assert channel.listen()
    try:
        with qtbot.waitSignal(channel.command_received, timeout=2000) as blocker:
            assert try_forward(["snapmock", "--capture", "window"], name=name)
        assert blocker.args == [["snapmock", "--capture", "window"]]
    finally:
        channel.close()
    assert not channel.is_listening


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"),
    reason="QLocalServer is a named pipe here, so no socket file can be stranded",
)
def test_channel_recovers_from_stale_endpoint(qtbot: QtBot) -> None:
    # A bare name lands in the system temp directory, where a crashed instance
    # would leave its socket file behind: bound, then abandoned without unlinking.
    name = f"snapmock-stale-{uuid.uuid4().hex[:8]}"
    path = Path(tempfile.gettempdir()) / name
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()
    assert path.exists()
    channel = SingleInstanceChannel(name)
    try:
        assert channel.listen()
    finally:
        channel.close()
    assert not path.exists()


def test_parse_command_line_separates_files_from_the_capture_options() -> None:
    """Packaging silence 2: the desktop entry's %F and a shell name files positionally."""
    command, files = parse_command_line(["snapmock"])
    assert command is None and files == []
    command, files = parse_command_line(["snapmock", "a.smk", "b.snagx"])
    assert command is None and files == ["a.smk", "b.snagx"]
    command, files = parse_command_line(
        ["snapmock", "--capture", "region", "--delay", "3", "c.smk"]
    )
    assert command is not None and command.mode == "region" and command.delay_seconds == 3
    assert files == ["c.smk"]
    command, files = parse_command_line(["--capture=full", "d.smk"])
    assert command is not None and command.mode == "full" and files == ["d.smk"]
    command, files = parse_command_line(["snapmock", "--unknown", "e.smk"])
    assert command is None and files == ["e.smk"]
