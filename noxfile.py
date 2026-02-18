"""Nox session definitions mirroring repository quality gates."""

from __future__ import annotations

import nox

nox.options.sessions = ["lint", "typecheck", "tests"]


@nox.session
def lint(session: nox.Session) -> None:
    """Run lint and formatting checks without mutating files."""
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(name="lint-fix")
def lint_fix(session: nox.Session) -> None:
    """Apply ruff fixes and formatting."""
    session.install("ruff")
    session.run("ruff", "check", "--fix", ".")
    session.run("ruff", "format", ".")


@nox.session
def typecheck(session: nox.Session) -> None:
    """Run mypy on source package with project dependencies installed."""
    session.install("mypy")
    session.install("-e", ".")
    session.run("mypy", "src")


@nox.session
def tests(session: nox.Session) -> None:
    """Run pytest against repository test suite."""
    session.install("pytest")
    session.install("-e", ".")
    session.run("pytest")


@nox.session(python=False)
def local(session: nox.Session) -> None:
    """Run local toolchain directly from current environment (no virtualenv)."""
    session.run("ruff", "check", "--fix", ".", external=True)
    session.run("ruff", "format", ".", external=True)

    session.run("mypy", "src", external=True)

    session.run("pytest", external=True)
