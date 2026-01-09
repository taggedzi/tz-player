"""Nox sessions."""

from __future__ import annotations

import nox

nox.options.sessions = ["lint", "lint-fix", "typecheck", "tests"]


@nox.session
def lint(session: nox.Session) -> None:
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(name="lint-fix")
def lint_fix(session: nox.Session) -> None:
    """Apply ruff fixes and formatting."""
    session.install("ruff")
    session.run("ruff", "format", ".")
    session.run("ruff", "check", "--fix", ".")


@nox.session
def typecheck(session: nox.Session) -> None:
    session.install("mypy")
    session.install("-e", ".")
    session.run("mypy", "src")


@nox.session
def tests(session: nox.Session) -> None:
    session.install("pytest")
    session.install("-e", ".")
    session.run("pytest")


@nox.session(python=False)
def local(session: nox.Session) -> None:
    session.run("ruff", "check", ".", external=True)
    session.run("ruff", "check", "--fix", ".", external=True)
    session.run("ruff", "format", "--check", ".", external=True)

    session.run("mypy", "src", external=True)

    session.run("pytest", external=True)
