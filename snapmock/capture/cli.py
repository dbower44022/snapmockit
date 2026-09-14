"""Command-line invocation (PRD 3.5): ``snapmock --capture <mode> [--delay N]``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CaptureCommand:
    """A capture request parsed from a command line. ``mode`` None means the default."""

    mode: str | None = None
    delay_seconds: int | None = None


def parse_capture_args(argv: list[str]) -> CaptureCommand | None:
    """Return the capture command in *argv*, or None when no capture was requested.

    Accepts ``--capture``, ``--capture <mode>``, ``--capture=<mode>``,
    ``--delay <seconds>`` and ``--delay=<seconds>``. Unknown arguments are ignored.
    """
    return parse_command_line(argv)[0]


def parse_command_line(argv: list[str]) -> tuple[CaptureCommand | None, list[str]]:
    """The capture command in *argv*, if any, and the files named on it.

    *argv* is a whole command line; its first element is the program unless it is
    an option. A file is any later argument that does not start with ``-`` and is
    not the value of ``--capture`` or ``--delay``; the desktop entry's ``%F`` and
    a shell both pass files that way (packaging silence 2). Unknown options are
    ignored.
    """
    command: CaptureCommand | None = None
    delay: int | None = None
    files: list[str] = []
    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--capture" or arg.startswith("--capture="):
            command = command or CaptureCommand()
            if "=" in arg:
                command.mode = arg.split("=", 1)[1] or None
            elif i + 1 < len(args) and not args[i + 1].startswith("-"):
                command.mode = args[i + 1]
                i += 1
        elif arg == "--delay" or arg.startswith("--delay="):
            text = arg.split("=", 1)[1] if "=" in arg else ""
            if not text and i + 1 < len(args):
                text = args[i + 1]
                i += 1
            try:
                delay = max(0, min(60, int(text)))
            except ValueError:
                delay = None
        elif i > 0 and not arg.startswith("-"):
            files.append(arg)
        i += 1
    if command is not None:
        command.delay_seconds = delay
    return command, files
