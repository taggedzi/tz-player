#!/usr/bin/env python3
"""
py_tree.py — show a class/method/attribute tree for a Python file.

Examples:
  python tools/py_tree.py src/rhythm_slicer/tui.py
  python tools/py_tree.py src/rhythm_slicer/tui.py --lines
  python tools/py_tree.py src/rhythm_slicer/tui.py --no-private
  python tools/py_tree.py src/rhythm_slicer/tui.py --only methods --lines
  python tools/py_tree.py src/rhythm_slicer/tui.py --no-group
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import os
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


# ----------------------------
# Optional rich support
# ----------------------------
def _try_import_rich():
    try:
        from rich.console import Console  # type: ignore
        from rich.tree import Tree  # type: ignore
        from rich.text import Text  # type: ignore

        return Console, Tree, Text
    except Exception:
        return None, None, None


Console, RichTree, RichText = _try_import_rich()


# ----------------------------
# Data model
# ----------------------------
@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def fmt(self, show: bool) -> str:
        if not show:
            return ""
        if self.start <= 0 and self.end <= 0:
            return " [?:?]"
        if self.end <= 0:
            return f" [{self.start}:?]"
        if self.start == self.end:
            return f" [{self.start}]"
        return f" [{self.start}-{self.end}]"


@dataclass
class Item:
    name: str
    span: Span


@dataclass
class ClassInfo:
    name: str
    span: Span
    methods: List[Item] = dataclasses.field(default_factory=list)
    attrs_class: List[Item] = dataclasses.field(default_factory=list)
    attrs_instance: List[Item] = dataclasses.field(default_factory=list)


# ----------------------------
# Helpers
# ----------------------------
def is_private(name: str) -> bool:
    # Treat __dunder__ and _private as "private-ish" for filtering.
    return name.startswith("_")


def node_span(node: ast.AST) -> Span:
    start = getattr(node, "lineno", 0) or 0
    end = getattr(node, "end_lineno", 0) or 0
    if start and not end:
        end = start
    return Span(start=start, end=end)


def safe_read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def dedupe_items(items: Iterable[Item]) -> List[Item]:
    # Dedupe by stable key (fixes your "unhashable Item" issue).
    seen: Dict[Tuple[str, int, int], Item] = {}
    for it in items:
        key = (it.name, it.span.start, it.span.end)
        # Keep first occurrence; you can change this if you prefer "latest wins".
        if key not in seen:
            seen[key] = it
    return list(seen.values())


# ----------------------------
# AST Analyzer
# ----------------------------
class Analyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: List[ClassInfo] = []
        self.module_functions: List[Item] = []
        self._class_stack: List[ClassInfo] = []
        self._func_stack: List[ast.FunctionDef | ast.AsyncFunctionDef] = []

    def current_class(self) -> Optional[ClassInfo]:
        return self._class_stack[-1] if self._class_stack else None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        ci = ClassInfo(name=node.name, span=node_span(node))
        self._class_stack.append(ci)

        # Walk class body
        self.generic_visit(node)

        # Dedupe + sort
        ci.methods = sorted(dedupe_items(ci.methods), key=lambda it: (it.name, it.span.start, it.span.end))
        ci.attrs_class = sorted(dedupe_items(ci.attrs_class), key=lambda it: (it.name, it.span.start, it.span.end))
        ci.attrs_instance = sorted(dedupe_items(ci.attrs_instance), key=lambda it: (it.name, it.span.start, it.span.end))

        self._class_stack.pop()
        self.classes.append(ci)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        ci = self.current_class()
        if ci is not None:
            ci.methods.append(Item(name=node.name, span=node_span(node)))
        elif not self._func_stack:
            self.module_functions.append(Item(name=node.name, span=node_span(node)))

        self._func_stack.append(node)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        self._handle_assign_like(node, targets=node.targets)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        targets = [node.target]
        self._handle_assign_like(node, targets=targets)

    def _handle_assign_like(self, node: ast.AST, targets: List[ast.expr]) -> None:
        ci = self.current_class()
        if ci is None:
            return

        # Only consider assignments occurring directly in a class body
        # as class attributes OR inside methods as instance attrs.
        in_method = bool(self._func_stack)

        for t in targets:
            # class attribute: NAME = ...
            if isinstance(t, ast.Name) and not in_method:
                ci.attrs_class.append(Item(name=t.id, span=node_span(node)))
                continue

            # instance attribute: self.NAME = ...
            if isinstance(t, ast.Attribute) and in_method:
                if isinstance(t.value, ast.Name) and t.value.id == "self":
                    ci.attrs_instance.append(Item(name=t.attr, span=node_span(node)))
                    continue

        self.generic_visit(node)


# ----------------------------
# Rendering (rich or plain)
# ----------------------------
def _style_for(kind: str) -> str:
    # Rich style names; ignored in plain output.
    return {
        "file": "bold cyan",
        "class": "bold magenta",
        "method": "green",
        "attr_class": "yellow",
        "attr_inst": "bright_yellow",
        "group": "bold white",
        "dim": "dim",
    }.get(kind, "")


def _label(name: str, kind: str, span: Span, show_lines: bool) -> str:
    return f"{name}{span.fmt(show_lines)}"


def render_rich(
    path: str,
    classes: List[ClassInfo],
    module_functions: List[Item],
    *,
    show_lines: bool,
    include_private: bool,
    only: str,
    group: bool,
) -> int:
    console = Console()
    root = RichTree(RichText(_label(os.path.relpath(path), "file", Span(0, 0), False), style=_style_for("file")))

    def ok_name(n: str) -> bool:
        return include_private or not is_private(n)

    module_functions = [m for m in module_functions if ok_name(m.name)]
    if only in ("all", "methods") and module_functions:
        if group:
            mn = root.add(RichText("module functions", style=_style_for("group")))
            for m in module_functions:
                mn.add(RichText(_label(m.name + "()", "method", m.span, show_lines), style=_style_for("method")))
        else:
            for m in module_functions:
                root.add(RichText(_label("function " + m.name + "()", "method", m.span, show_lines), style=_style_for("method")))

    for ci in sorted(classes, key=lambda c: (c.name, c.span.start, c.span.end)):
        if not include_private and is_private(ci.name):
            continue

        class_node = root.add(RichText(_label(f"class {ci.name}", "class", ci.span, show_lines), style=_style_for("class")))

        if only == "classes":
            continue

        methods = [m for m in ci.methods if ok_name(m.name)]
        cattrs = [a for a in ci.attrs_class if ok_name(a.name)]
        iattrs = [a for a in ci.attrs_instance if ok_name(a.name)]

        if only in ("all", "methods"):
            if group:
                mn = class_node.add(RichText("methods", style=_style_for("group")))
                for m in methods:
                    mn.add(RichText(_label(m.name + "()", "method", m.span, show_lines), style=_style_for("method")))
            else:
                for m in methods:
                    class_node.add(RichText(_label("method " + m.name + "()", "method", m.span, show_lines), style=_style_for("method")))

        if only in ("all", "attrs"):
            if group:
                cn = class_node.add(RichText("class attrs", style=_style_for("group")))
                for a in cattrs:
                    cn.add(RichText(_label(a.name, "attr_class", a.span, show_lines), style=_style_for("attr_class")))
                inn = class_node.add(RichText("instance attrs", style=_style_for("group")))
                for a in iattrs:
                    inn.add(RichText(_label("self." + a.name, "attr_inst", a.span, show_lines), style=_style_for("attr_inst")))
            else:
                for a in cattrs:
                    class_node.add(RichText(_label("class_attr " + a.name, "attr_class", a.span, show_lines), style=_style_for("attr_class")))
                for a in iattrs:
                    class_node.add(RichText(_label("inst_attr self." + a.name, "attr_inst", a.span, show_lines), style=_style_for("attr_inst")))

    console.print(root)
    return 0


def render_plain(
    path: str,
    classes: List[ClassInfo],
    module_functions: List[Item],
    *,
    show_lines: bool,
    include_private: bool,
    only: str,
    group: bool,
) -> int:
    def ok_name(n: str) -> bool:
        return include_private or not is_private(n)

    def line(s: str) -> None:
        print(s)

    line(os.path.relpath(path))

    module_functions = [m for m in module_functions if ok_name(m.name)]
    if only in ("all", "methods") and module_functions:
        if group:
            line("├── module functions")
            for i, m in enumerate(module_functions):
                is_last = (i == len(module_functions) - 1)
                line(f"│   {'└──' if is_last else '├──'} {m.name}(){m.span.fmt(show_lines)}")
        else:
            for m in module_functions:
                line(f"├── function {m.name}(){m.span.fmt(show_lines)}")

    for ci in sorted(classes, key=lambda c: (c.name, c.span.start, c.span.end)):
        if not include_private and is_private(ci.name):
            continue

        line(f"└── class {ci.name}{ci.span.fmt(show_lines)}")

        if only == "classes":
            continue

        methods = [m for m in ci.methods if ok_name(m.name)]
        cattrs = [a for a in ci.attrs_class if ok_name(a.name)]
        iattrs = [a for a in ci.attrs_instance if ok_name(a.name)]

        # Helper to print children with nice branch chars
        def print_group(title: str, items: List[str], last_group: bool) -> None:
            prefix = "    "
            line(f"{prefix}{'└──' if last_group else '├──'} {title}")
            for i, it in enumerate(items):
                is_last = (i == len(items) - 1)
                stem = "        " if last_group else "    │   "
                line(f"{stem}{'└──' if is_last else '├──'} {it}")

        child_blocks: List[Tuple[str, List[str]]] = []

        if only in ("all", "methods"):
            if group:
                child_blocks.append(
                    ("methods", [f"{m.name}(){m.span.fmt(show_lines)}" for m in methods])
                )
            else:
                for m in methods:
                    line(f"    ├── method {m.name}(){m.span.fmt(show_lines)}")

        if only in ("all", "attrs"):
            if group:
                child_blocks.append(
                    ("class attrs", [f"{a.name}{a.span.fmt(show_lines)}" for a in cattrs])
                )
                child_blocks.append(
                    ("instance attrs", [f"self.{a.name}{a.span.fmt(show_lines)}" for a in iattrs])
                )
            else:
                for a in cattrs:
                    line(f"    ├── class_attr {a.name}{a.span.fmt(show_lines)}")
                for a in iattrs:
                    line(f"    ├── inst_attr self.{a.name}{a.span.fmt(show_lines)}")

        if group:
            # Print grouped blocks (skip empty)
            nonempty = [(t, its) for (t, its) in child_blocks if its]
            for bi, (t, its) in enumerate(nonempty):
                print_group(t, its, last_group=(bi == len(nonempty) - 1))

    return 0


# ----------------------------
# CLI
# ----------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Print a tree of classes/methods/attributes in a Python file.")
    p.add_argument("path", help="Path to a .py file")

    p.add_argument("--lines", dest="lines", action="store_true", help="Show line spans [start-end]")
    p.add_argument("--no-lines", dest="lines", action="store_false", help="Do not show line spans")
    p.set_defaults(lines=False)

    p.add_argument("--private", dest="private", action="store_true", help="Include private members (default)")
    p.add_argument("--no-private", dest="private", action="store_false", help="Exclude private members (_x, __dunder__)")
    p.set_defaults(private=True)

    p.add_argument(
        "--only",
        choices=["all", "classes", "methods", "attrs"],
        default="all",
        help="Limit output to certain element types",
    )

    p.add_argument("--group", dest="group", action="store_true", help="Group into Methods / Class attrs / Instance attrs (default)")
    p.add_argument("--no-group", dest="group", action="store_false", help="Do not group; print flat children")
    p.set_defaults(group=True)

    p.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        help="Disable colored output even if rich is installed",
    )
    p.set_defaults(color=True)

    return p


def main(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    path = args.path

    if not os.path.isfile(path):
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    if not path.lower().endswith(".py"):
        print("warning: file does not end with .py; attempting parse anyway", file=sys.stderr)

    try:
        source = safe_read_text(path)
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        print(f"error: SyntaxError: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: could not read file: {e}", file=sys.stderr)
        return 1

    analyzer = Analyzer()
    analyzer.visit(tree)
    module_functions = sorted(
        dedupe_items(analyzer.module_functions),
        key=lambda it: (it.name, it.span.start, it.span.end),
    )

    use_rich = bool(Console and RichTree and RichText and args.color)
    if use_rich:
        return render_rich(
            path,
            analyzer.classes,
            module_functions,
            show_lines=args.lines,
            include_private=args.private,
            only=args.only,
            group=args.group,
        )
    return render_plain(
        path,
        analyzer.classes,
        module_functions,
        show_lines=args.lines,
        include_private=args.private,
        only=args.only,
        group=args.group,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
