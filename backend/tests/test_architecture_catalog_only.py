"""Nothing outside the catalog defines a tool. [RM-07]

The architecture rule of the remediation run is ONE CALCULATION, MANY ADAPTERS: the capability catalog is the
only source of a tool's name, description, argument schema and kind, and every surface (the MAF tools in the
orchestrator, the MCP facade, the gateway) is a generated adapter over it. A rule that is only written down
drifts, so this scans the adapters:

- no tool DEFINITION is constructed outside the catalog and the one factory (`FunctionTool(...)`,
  `CapabilitySpec(...)`, a `ToolSpec(...)` with a literal in it, a decorator that makes a tool);
- no dict shaped like a tool definition carries a literal name or description, and no inline JSON schema
  (`{"type": "object", "properties": ...}`) is written in an adapter;
- no string copies, or edits, a catalog description or one of the catalog's channel sentences;
- a catalog tool NAME appears as a literal only where a named reference is listed here with its reason.

The scanners take source text so the tests below can prove they bite, not only that today's tree is clean.
Where the rule needs an exception the exception is a named entry in this file, never a loosened pattern.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from application.capabilities import catalog

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_ROOTS = (ROOT / "channel_orchestrator" / "app", ROOT / "backend" / "channel")
FACTORY = "maf_catalog_tools.py"
#: A tool-definition construction: only the factory may call these with the catalog's words.
DEFINERS = frozenset({"FunctionTool", "CapabilitySpec", "ToolSpec"})
#: Constructors of a different, framework-owned wire type that carries what the factory generated, never a literal.
BRIDGES = {"ToolSpec": {"maf_agent.py"}}
MAX_CITED = 40

#: Where a catalog tool name is written as a literal, and why. Referring to a tool is not defining one: these
#: are routing and policy decisions ABOUT a named tool (which results are not recorded, how a package link is
#: made), each keyed by file. A new reference fails the test until it is listed with a reason.
NAMED_REFERENCES = {
    "downloads.py": "the download route spends a package-link ticket through the gateway's one pipeline",
    "ledger.py": "the gateway's fact ledger does not record these tools' results (positions and counts, not facts)",
    "pipeline.py": "the gateway answers verify_figures and the package link itself, and routes a commit by its prepare name",
    "writes.py": "the confirm path builds the commit tool's name from the prepared tool's and asks for the package link",
}


def _catalog_names() -> set[str]:
    return {s.name for s in catalog.CATALOG} | {s.name for s in catalog.DIAGNOSTICS}


def _words() -> list[str]:
    """Every sentence a surface could copy: each tool's description and the catalog's two channel sentences."""
    return [*(s.description for s in (*catalog.CATALOG, *catalog.DIAGNOSTICS)), catalog.PREVIEW_SENTENCE, catalog.COMMIT_SENTENCE]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def _called(node: ast.Call) -> str:
    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""


def _is_literal_text(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)) or isinstance(node, ast.JoinedStr)


def _keys(node: ast.Dict) -> dict[str, ast.AST]:
    return {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def definitions(source: str, filename: str) -> list[str]:
    """Tool definitions written in `source` (a file named `filename`) that the catalog should own."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _called(node) in DEFINERS:
            name, allowed = _called(node), BRIDGES.get(_called(node), set())
            literal = any(_is_literal_text(a) for a in (*node.args, *(k.value for k in node.keywords)))
            if filename not in allowed and not (name == "FunctionTool" and filename == FACTORY) or literal:
                found.append(f"{filename}:{node.lineno} constructs {name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found += [f"{filename}:{node.lineno} decorates a tool" for d in node.decorator_list if "tool" in ast.unparse(d).lower().split("(")[0]]
        if isinstance(node, ast.Dict):
            shape = _keys(node)
            if shape.get("type") and "properties" in shape and isinstance(shape["type"], ast.Constant) and shape["type"].value == "object":
                found.append(f"{filename}:{node.lineno} writes an inline JSON schema")
            if "name" in shape and {"inputSchema", "input_schema", "parameters"} & shape.keys():
                if any(_is_literal_text(shape.get(k)) for k in ("name", "description") if k in shape):
                    found.append(f"{filename}:{node.lineno} writes a tool definition with a literal name or description")
    return found


def copied_words(source: str, filename: str) -> list[str]:
    """String literals that repeat, or edit, a catalog description or channel sentence."""
    tree, found = ast.parse(source), []
    skip, words = _docstring_nodes(tree), _words()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in skip:
            continue
        text = " ".join(node.value.split())
        if len(text) < 30:
            continue
        for word in words:
            flat = " ".join(word.split())
            if flat[:MAX_CITED] in text or text in flat:
                found.append(f"{filename}:{node.lineno} repeats catalog words: {text[:50]!r}")
                break
    return found


def named_references(source: str, filename: str) -> list[str]:
    """Catalog tool names written as literals in `source`, one per occurrence."""
    names, tree = _catalog_names(), ast.parse(source)
    skip = _docstring_nodes(tree)
    return [
        f"{filename}:{n.lineno} names {n.value}" for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in names and id(n) not in skip
    ]


def _sources() -> list[Path]:
    return sorted(p for root in ADAPTER_ROOTS for p in root.rglob("*.py") if "vendor" not in p.parts and "__pycache__" not in p.parts)


def test_the_adapters_exist_to_be_scanned():
    names = {p.name for p in _sources()}
    assert {"maf_catalog_tools.py", "maf_agent.py", "mcp.py", "tools.py", "pipeline.py"} <= names


@pytest.mark.parametrize("path", _sources(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_adapter_defines_a_tool_or_copies_the_catalogs_words(path):
    source = path.read_text(encoding="utf-8")
    problems = [*definitions(source, path.name), *copied_words(source, path.name)]
    assert not problems, "the catalog is the only source of a tool's name, description and schema:\n  " + "\n  ".join(problems)


def test_a_catalog_tool_name_is_a_literal_only_where_a_reference_is_listed_with_its_reason():
    unlisted = [
        f"{p.parent.name}/{hit}" for p in _sources() for hit in named_references(p.read_text(encoding="utf-8"), p.name)
        if p.name not in NAMED_REFERENCES
    ]
    assert not unlisted, "name the tool through the catalog, or list the reference (and why) in NAMED_REFERENCES:\n  " + "\n  ".join(unlisted)


def test_every_listed_reference_still_exists_so_the_list_cannot_go_stale():
    used = {p.name for p in _sources() if named_references(p.read_text(encoding="utf-8"), p.name)}
    assert set(NAMED_REFERENCES) <= used, f"remove from NAMED_REFERENCES: {sorted(set(NAMED_REFERENCES) - used)}"
    assert all(NAMED_REFERENCES.values()), "every listed reference carries its reason"


def test_the_mcp_facade_and_the_gateways_tool_list_read_the_catalog():
    mcp = (ROOT / "backend" / "channel" / "mcp.py").read_text(encoding="utf-8")
    tools = (ROOT / "backend" / "channel" / "tools.py").read_text(encoding="utf-8")
    assert "catalog.channel_description(spec)" in mcp and "catalog.behaviour_hints(spec)" in mcp
    assert "catalog.offered_for_channel(" in tools


# ---------------------------------------------------------------- the scanners bite


def test_a_function_tool_built_outside_the_factory_is_found():
    assert definitions("FunctionTool(name=n, func=f)", "somewhere.py")
    assert not definitions("FunctionTool(name=spec.name, description=spec.description, func=f)", FACTORY)


def test_a_literal_in_a_tool_definition_is_found_even_in_the_factory():
    assert definitions('FunctionTool(name="client_trend", func=f)', FACTORY)
    assert definitions('ToolSpec("x", "words", {})', "maf_agent.py")
    assert not definitions("ToolSpec(t.name, t.description, t.parameters())", "maf_agent.py")
    assert definitions("ToolSpec(t.name, t.description, t.parameters())", "planner.py")


def test_a_capability_spec_and_a_tool_decorator_are_found_in_an_adapter():
    assert definitions('CapabilitySpec(name="x")', "tools.py")
    assert definitions("@tool\nasync def f(): ...", "tools.py")
    assert definitions("@agent_framework.tool(name='x')\ndef f(): ...", "tools.py")


def test_a_dict_that_is_a_tool_definition_is_found_and_one_built_from_a_spec_is_not():
    assert definitions('{"name": "x", "description": "d", "inputSchema": s}', "mcp.py")
    assert not definitions('{"name": spec.name, "description": spec.description, "inputSchema": spec.schema}', "mcp.py")


def test_an_inline_json_schema_is_found():
    assert definitions('x = {"type": "object", "properties": {}}', "tools.py")
    assert not definitions('x = {"type": "object"}', "tools.py")


def test_a_copied_or_edited_description_is_found_and_a_docstring_quoting_it_is_not():
    description = catalog.BY_NAME["book_rank"].description
    assert copied_words(f"x = {description!r}", "a.py")
    assert copied_words(f"x = {(description + ' And more.')!r}", "a.py")
    assert copied_words(f"x = {catalog.PREVIEW_SENTENCE!r}", "a.py")
    assert copied_words(f"x = {description[5:60]!r}", "a.py")
    assert not copied_words(f'def f():\n    """{description}"""\n    return 1', "a.py")
    assert not copied_words("x = 'a short unrelated sentence that is long enough to count'", "a.py")


def test_a_literal_tool_name_is_found_and_a_name_in_a_docstring_is_not():
    assert named_references('x = "client_trend"', "a.py") and named_references('x = "channel_ping"', "a.py")
    assert not named_references('def f():\n    """client_trend"""', "a.py")
    assert not named_references('x = "not_a_tool"', "a.py")
