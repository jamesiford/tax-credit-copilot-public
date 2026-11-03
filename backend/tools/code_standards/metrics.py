"""Measure one Python file against the coding standards. [AI-08]

Pure AST: no imports of the code under test, so it cannot be fooled by (or crash on)
what it measures. Each finding is a `(key, value)` pair — the key names WHAT and
WHERE (`function-lines|api/x.py::Foo.bar`), the value says HOW BAD — which is what
the ratchet in `baseline.py` compares.

The standards (new and touched code):

| rule              | limit | key prefix        |
| ----------------- | ----- | ----------------- |
| module lines      | 250   | `module-lines`    |
| class lines       | 150   | `class-lines`     |
| function lines    | 40    | `function-lines`  |
| cyclomatic number | 10    | `complexity`      |
| arguments         | 7     | `args`            |
| bare `except:`    | 0     | `bare-except`     |
| module docstring  | yes   | `docstring-module`|
| public class doc  | yes   | `docstring-class` |
| public function doc (over 15 lines) | yes | `docstring-function` |

Why those numbers: a unit that fits on one screen and branches ten ways or fewer can
be read, tested and reasoned about whole; past that, people stop reading it and start
trusting it. Docstrings are required where a reader meets a public name and has to
decide whether to trust it; a docstring should say WHY, which no tool can check, so
only its presence is enforced.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass

LIMITS = {"module-lines": 250, "class-lines": 150, "function-lines": 40, "complexity": 10, "args": 7}
DOCSTRING_FUNCTION_MIN_LINES = 15

_BRANCHES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True)
class Finding:
    """One standard a file breaks (`key`: rule and place) and by how much (`value`)."""

    key: str
    value: int


def _span(node: ast.AST) -> int:
    return getattr(node, "end_lineno", node.lineno) - node.lineno + 1


def complexity(function: ast.AST) -> int:
    """McCabe's number for one function: 1 + decision points, not counting nested functions."""
    total = 1
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (*_FUNCTIONS, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, _BRANCHES):
            total += 1
        elif isinstance(node, ast.BoolOp):
            total += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            total += 1 + len(node.ifs)
        elif isinstance(node, ast.match_case):
            total += 1
        stack.extend(ast.iter_child_nodes(node))
    return total


def _arg_count(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    a = function.args
    names = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    return len([n for n in names if n.arg not in ("self", "cls")]) + bool(a.vararg) + bool(a.kwarg)


def _walk(body: list[ast.stmt], prefix: str = "") -> Iterator[tuple[str, ast.AST]]:
    """Every class and function with its dotted name, nested ones included."""
    for node in body:
        if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
            name = f"{prefix}{node.name}"
            yield name, node
            yield from _walk(node.body, name + ".")


def _bare_excepts(node: ast.AST) -> int:
    return sum(isinstance(n, ast.ExceptHandler) and n.type is None for n in ast.walk(node))


def _function_findings(path: str, name: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[Finding]:
    where, lines = f"{path}::{name}", _span(node)
    if lines > LIMITS["function-lines"]:
        yield Finding(f"function-lines|{where}", lines)
    if (c := complexity(node)) > LIMITS["complexity"]:
        yield Finding(f"complexity|{where}", c)
    if (n := _arg_count(node)) > LIMITS["args"]:
        yield Finding(f"args|{where}", n)
    if lines > DOCSTRING_FUNCTION_MIN_LINES and not name.split(".")[-1].startswith("_") and not ast.get_docstring(node):
        yield Finding(f"docstring-function|{where}", 1)


def _class_findings(path: str, name: str, node: ast.ClassDef) -> Iterator[Finding]:
    if (lines := _span(node)) > LIMITS["class-lines"]:
        yield Finding(f"class-lines|{path}::{name}", lines)
    if not name.split(".")[-1].startswith("_") and not ast.get_docstring(node):
        yield Finding(f"docstring-class|{path}::{name}", 1)


def measure(path: str, source: str) -> list[Finding]:
    """Every standard `source` breaks, as findings keyed by `path` (use forward slashes)."""
    tree = ast.parse(source)
    found: list[Finding] = []
    if (n := len(source.splitlines())) > LIMITS["module-lines"]:
        found.append(Finding(f"module-lines|{path}", n))
    if not ast.get_docstring(tree):
        found.append(Finding(f"docstring-module|{path}", 1))
    for name, node in _walk(tree.body):
        if isinstance(node, ast.ClassDef):
            found.extend(_class_findings(path, name, node))
        else:
            found.extend(_function_findings(path, name, node))
            if bare := _bare_excepts(node):
                found.append(Finding(f"bare-except|{path}::{name}", bare))
    return found
