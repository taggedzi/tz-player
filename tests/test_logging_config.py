"""Tests for logging configuration and entrypoint wiring."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import tz_player.app as app_module
import tz_player.cli as cli_module
import tz_player.gui as gui_module
from tz_player.logging_utils import setup_logging


def _flush_root_handlers() -> None:
    for handler in logging.getLogger().handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()


def test_setup_logging_default_path_writes_log(tmp_path) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        setup_logging(log_dir=tmp_path, level="INFO")
        logger = logging.getLogger("tz_player.test")
        logger.info("default-log-path")
        _flush_root_handlers()
        log_path = tmp_path / "tz-player.log"
        assert log_path.exists()
        assert "default-log-path" in log_path.read_text(encoding="utf-8")
    finally:
        root.handlers.clear()
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_setup_logging_custom_log_file_writes_log(tmp_path) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    custom_path = tmp_path / "custom" / "player.log"
    try:
        setup_logging(log_dir=tmp_path, level="DEBUG", log_file=custom_path)
        logger = logging.getLogger("tz_player.test")
        logger.debug("custom-log-path")
        _flush_root_handlers()
        assert custom_path.exists()
        assert "custom-log-path" in custom_path.read_text(encoding="utf-8")
    finally:
        root.handlers.clear()
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_cli_main_passes_effective_level_and_log_file(monkeypatch, tmp_path) -> None:
    args = SimpleNamespace(
        verbose=True,
        quiet=True,
        log_file=str(tmp_path / "cli.log"),
        backend="fake",
    )
    captured: dict[str, object] = {}

    class FakeParser:
        def parse_args(self):
            return args

    def fake_setup_logging(*, log_dir: Path, level: str, log_file: Path | None):
        captured["log_dir"] = log_dir
        captured["level"] = level
        captured["log_file"] = log_file

    monkeypatch.setattr(cli_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_module, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli_module, "log_dir", lambda: tmp_path / "logs")

    rc = cli_module.main()

    assert rc == 0
    assert captured["level"] == "WARNING"
    assert captured["log_file"] == tmp_path / "cli.log"


def test_gui_main_passes_effective_level_and_log_file(monkeypatch, tmp_path) -> None:
    args = SimpleNamespace(
        verbose=False,
        quiet=False,
        log_file=str(tmp_path / "gui.log"),
        backend="vlc",
    )
    captured: dict[str, object] = {}

    class FakeParser:
        def parse_args(self):
            return args

    class FakeApp:
        def __init__(self, *, backend_name: str | None = None) -> None:
            captured["backend"] = backend_name

        def run(self) -> None:
            captured["ran"] = True

    def fake_setup_logging(*, log_dir: Path, level: str, log_file: Path | None):
        captured["log_dir"] = log_dir
        captured["level"] = level
        captured["log_file"] = log_file

    monkeypatch.setattr(gui_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(gui_module, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(gui_module, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(gui_module, "TzPlayerApp", FakeApp)

    rc = gui_module.main()

    assert rc == 0
    assert captured["level"] == "INFO"
    assert captured["log_file"] == tmp_path / "gui.log"
    assert captured["backend"] == "vlc"
    assert captured["ran"] is True


def test_app_main_passes_effective_level_and_log_file(monkeypatch, tmp_path) -> None:
    args = SimpleNamespace(
        verbose=True,
        quiet=False,
        log_file=str(tmp_path / "app.log"),
        backend="fake",
    )
    captured: dict[str, object] = {}

    class FakeParser:
        def parse_args(self):
            return args

    class FakeApp:
        def __init__(self, *, backend_name: str | None = None) -> None:
            captured["backend"] = backend_name

        def run(self) -> None:
            captured["ran"] = True

    def fake_setup_logging(*, log_dir: Path, level: str, log_file: Path | None):
        captured["log_dir"] = log_dir
        captured["level"] = level
        captured["log_file"] = log_file

    monkeypatch.setattr(app_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(app_module, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(app_module, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(app_module, "TzPlayerApp", FakeApp)

    rc = app_module.main()

    assert rc == 0
    assert captured["level"] == "DEBUG"
    assert captured["log_file"] == tmp_path / "app.log"
    assert captured["backend"] == "fake"
    assert captured["ran"] is True


def test_app_main_returns_nonzero_on_startup_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    args = SimpleNamespace(
        verbose=False,
        quiet=False,
        log_file=None,
        backend="fake",
    )

    class FakeParser:
        def parse_args(self):
            return args

    class FailingApp:
        def __init__(self, *, backend_name: str | None = None) -> None:
            del backend_name

        def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(app_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(app_module, "TzPlayerApp", FailingApp)

    rc = app_module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "Startup failed." in captured.err


def test_app_main_doctor_path_returns_report_exit_code(
    monkeypatch, tmp_path, capsys
) -> None:
    args = SimpleNamespace(
        command="doctor",
        verbose=False,
        quiet=False,
        log_file=None,
        backend="vlc",
    )

    class FakeParser:
        def parse_args(self):
            return args

    class ForbiddenApp:
        def __init__(self, *, backend_name: str | None = None) -> None:
            raise AssertionError("TUI app should not be constructed in doctor mode")

    class FakeReport:
        exit_code = 2

    monkeypatch.setattr(app_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(app_module, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(app_module, "run_doctor", lambda _backend: FakeReport())
    monkeypatch.setattr(app_module, "render_report", lambda _report: "doctor output")
    monkeypatch.setattr(app_module, "TzPlayerApp", ForbiddenApp)

    rc = app_module.main()
    captured = capsys.readouterr()

    assert rc == 2
    assert "doctor output" in captured.out


def test_gui_main_returns_nonzero_on_startup_failure(
    monkeypatch, tmp_path, capsys
) -> None:
    args = SimpleNamespace(
        verbose=False,
        quiet=False,
        log_file=None,
        backend="vlc",
    )

    class FakeParser:
        def parse_args(self):
            return args

    class FailingApp:
        def __init__(self, *, backend_name: str | None = None) -> None:
            del backend_name

        def run(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(gui_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(gui_module, "setup_logging", lambda **kwargs: None)
    monkeypatch.setattr(gui_module, "log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(gui_module, "TzPlayerApp", FailingApp)

    rc = gui_module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "GUI startup failed." in captured.err


def test_cli_main_returns_nonzero_when_logging_setup_fails(
    monkeypatch, tmp_path, capsys
) -> None:
    args = SimpleNamespace(
        verbose=False,
        quiet=False,
        log_file=None,
        backend="fake",
    )

    class FakeParser:
        def parse_args(self):
            return args

    def fail_setup_logging(**kwargs):
        del kwargs
        raise OSError("cannot open log")

    monkeypatch.setattr(cli_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_module, "setup_logging", fail_setup_logging)
    monkeypatch.setattr(cli_module, "log_dir", lambda: tmp_path / "logs")

    rc = cli_module.main()
    captured = capsys.readouterr()

    assert rc == 1
    assert "Unexpected error. Re-run with --verbose for details." in captured.err
