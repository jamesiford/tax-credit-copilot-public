"""Where each orchestration pattern is allowed, and that nothing that carries a figure computes one. [RM-10d]

The hosted orchestrator uses the Microsoft Agent Framework three ways, and each has one job:

- an **Agent** for open-ended questions (a model chooses which catalog tools to call);
- a **Workflow** for a fixed sequence (the client review pack) and for a confirmation (the write path);
- a **tool or executor body** that forwards a call and moves a message, and never touches a figure.

These tests state that as rules over the source, so a fourth use, a model inside a workflow, a loose sequence of tool
calls or a bit of arithmetic in an executor fails the build with the rule it broke. Each rule has a registry below:
adding to one is a deliberate edit with a stated reason, in the same change as the code that needs it.

The figure detector is the one that could be wrong quietly, so it is proved on seeded violations (including one
injected into a real executor's source) as well as on the real tree.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "channel_orchestrator" / "app"
CORE = APP / "core"
SOURCES = {p.name: p for p in sorted([*APP.glob("*.py"), *CORE.glob("*.py")])}

#: Where an Agent may be built, and why. An Agent is for an open question; the second is the framework's own way to
#: run function middleware (F-09: nothing public runs it without an Agent), for a tool a planner or a step names.
AGENTS = {
    "maf_agent.py": "the planner: a model chooses which catalog tools to call for an open question",
    "maf_tool_run.py": "one named tool through the same function middleware, for the degraded planners and the pack's steps (F-09)",
}
#: Where a Workflow may be built, and for which kind of job.
WORKFLOWS = {
    "maf_write_flow.py": "a confirmation: prepare, wait for the reader, commit",
    "maf_review_pack.py": "a fixed sequence: resolve, read the position, check, compose",
}
#: Modules that may define executors or use workflow primitives: the two above and the steps the first one builds.
WORKFLOW_MODULES = {"maf_write_steps.py", *WORKFLOWS}
PRIMITIVES = {"Executor", "WorkflowBuilder", "WorkflowContext", "Workflow", "handler", "response_handler"}
#: What a workflow module must never import: a model, a planner or an agent. A workflow is not open Q&A.
MODEL_SIDE = {"app.core.planner", "app.core.degraded", "app.core.models", "app.core.model_access", "app.core.maf_agent",
              "app.core.maf_chat", "app.core.maf_foundry_client", "app.core.prompts", "app.core.maf_tool_run"}
#: The modules a model's tool call may start a workflow from: the generated prepare tool's body, and nothing else.
OPEN_QA_MODULES = {"planner.py", "degraded.py", "maf_agent.py", "model_access.py", "models.py"}

#: Entry points into a pattern, and the only modules that may call them.
ENTRY_POINTS = {
    "run_review_pack": {"turn.py"}, "commit_pending": {"turn.py"}, "cancel_pending": {"turn.py"}, "drop_pending": {"turn.py"},
    "prepare_write": {"maf_write_flow.py"}, "build_agent": {"planner.py"},
}
#: The commit chain, by who may construct each link: (file, qualified function).
CONSTRUCTORS = {
    "Approved": {("maf_write_steps.py", "AwaitConfirmation.answered")},
    "Commit": {("maf_write_flow.py", "build_write_flow")},
    "PrepareRequest": {("maf_write_flow.py", "prepare_write")},
    "Confirmation": {("maf_write_flow.py", "commit_pending"), ("maf_write_flow.py", "cancel_pending")},
    "send_commit": {("maf_write_steps.py", "Commit.commit")},
}

#: A sequence of tool calls (two in one function, or one in a loop) outside an executor or the Agent, and why it may exist.
SEQUENCES = {
    ("degraded.py", "JsonPlanner._round"): "the degraded planner runs the tools a JSON plan names, in the plan's order (RM-10a)",
    ("degraded.py", "KeywordPlanner.plan"): "the degraded planner runs the tools the keyword table picks (RM-10a)",
}
TOOL_CALLS = {"call_tool", "forward", "_timed"}
TURN_NAMES = {"runner", "turn", "self._turn"}

#: Arithmetic a figure-free module may contain, by (file, function, statement), and why. Each is a counter or a
#: label suffix; none touches an envelope value. A new line here is a review question, not a convenience.
ARITHMETIC = {
    ("maf_tool_rules.py", "Budget.process", "turn.calls += 1"): "counts a call against the turn's tool budget: an integer counter",
    ("maf_tool_call.py", "CallAndCapture._every_method", "turn.calls += 1"): "the second certified method's call is counted against the same budget",
    ("maf_tool_call.py", "_label", "n + 1"): "numbers a label when two runs of one tool share it: a name, not a figure",
}
#: Functions outside the `maf_*` modules whose body is a tool body or runs inside an executor.
FIGURE_FREE_FUNCTIONS = {
    "tools.py": {"ToolRunner.forward", "ToolRunner._timed"},
    "writes.py": {"send_commit", "_package_link"},
}
#: Not scanned, and why: the chat client's loop limits are counts of model iterations, not a tool or an executor.
NOT_SCANNED = {"maf_chat.py": "loop limits for the model client: iteration counts, no tool body and no executor"}

ARITH = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
NUMBER_CALLS = frozenset({"round", "sum", "min", "max", "abs", "divmod", "pow", "format", "float", "Decimal", "quantize", "fsum", "mean"})
NUMBER_MODULES = frozenset({"math", "statistics", "decimal", "fractions", "numpy", "locale"})


# --------------------------------------------------------------------- the tree


def parse(name: str) -> ast.Module:
    return ast.parse(SOURCES[name].read_text(encoding="utf-8"))


def walk(node: ast.AST, owner: str = "<module>") -> Iterator[tuple[str, ast.AST]]:
    """Every node under `node` with the qualified name of the function or class it sits in."""
    for child in ast.iter_child_nodes(node):
        inside = owner
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inside = child.name if owner == "<module>" else f"{owner}.{child.name}"
        yield inside, child
        yield from walk(child, inside)


def name_of(call: ast.Call) -> str:
    return call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""


def callers(name: str) -> set[tuple[str, str]]:
    """(file, qualified function) for every call of `name(...)`, whoever the receiver is."""
    return {(f, owner) for f in SOURCES for owner, n in walk(parse(f)) if isinstance(n, ast.Call) and name_of(n) == name}


def importers(names: set[str]) -> set[str]:
    """The files that import any of `names` (as a module or as a member of one)."""
    found = set()
    for f in SOURCES:
        for _, n in walk(parse(f)):
            if isinstance(n, ast.ImportFrom) and (n.module or "") != "" and ({n.module, *(f"{n.module}.{a.name}" for a in n.names)} & names):
                found.add(f)
            if isinstance(n, ast.Import) and {a.name for a in n.names} & names:
                found.add(f)
    return found


def imported_members(file: str) -> set[str]:
    return {a.name for _, n in walk(parse(file)) if isinstance(n, ast.ImportFrom) for a in n.names}


# ---------------------------------------------------------- the figure detector


def _text(node: ast.AST) -> bool:
    """Text or a container display (so `+` and `*` on it are concatenation and repetition, not arithmetic)."""
    if isinstance(node, ast.IfExp):
        return _text(node.body) and _text(node.orelse)
    return isinstance(node, (ast.JoinedStr, ast.List, ast.Tuple, ast.Set, ast.Dict)) or (
        isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)))


def _int(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool)


def computes(node: ast.AST) -> str | None:
    """What `node` does to a number, or None: arithmetic, a number-shaped call, a formatted number, a maths import."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ARITH):
        if isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            return "formats with %"
        return None if (_int(node.left) and _int(node.right)) or _text(node.left) or _text(node.right) else "arithmetic"
    if isinstance(node, ast.AugAssign) and isinstance(node.op, ARITH):
        return None if _text(node.value) else "arithmetic"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and not isinstance(node.operand, ast.Constant):
        return "negation"
    if isinstance(node, ast.Call) and (name_of(node) in NUMBER_CALLS or (isinstance(node.func, ast.Attribute) and node.func.attr == "format")):
        return "number call"
    if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
        return "formatted number"
    modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
    return "maths import" if any(m.split(".")[0] in NUMBER_MODULES for m in modules) else None


def figure_computations(source: str, only: set[str] | None = None) -> list[tuple[str, int, str, str]]:
    """(function, line, what, statement) for each place `source` computes or formats a number; `only` limits it to functions."""
    return [
        (owner, n.lineno, what, ast.unparse(n)) for owner, n in walk(ast.parse(source))
        if (what := computes(n)) and (only is None or owner in only or any(owner.startswith(o + ".") for o in only))
    ]


def own_calls(function: ast.AST, in_loop: bool = False) -> Iterator[tuple[ast.Call, bool]]:
    """The calls in a function's own body (not in a function defined inside it), each with whether a loop holds it."""
    for child in ast.iter_child_nodes(function):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        looping = in_loop or isinstance(child, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
        if isinstance(child, ast.Call):
            yield child, looping
        yield from own_calls(child, looping)


def is_tool_call(call: ast.Call) -> bool:
    receiver = ast.unparse(call.func.value) if isinstance(call.func, ast.Attribute) else ""
    return name_of(call) in TOOL_CALLS or (name_of(call) == "run" and receiver in TURN_NAMES)


def tool_call_sequences(source: str) -> set[str]:
    """Qualified functions that run two or more tools, or one in a loop: a sequence nobody framed as a workflow."""
    found = set()
    for owner, node in walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sites = [looping for call, looping in own_calls(node) if is_tool_call(call)]
            if len(sites) >= 2 or any(sites):
                found.add(owner)
    return found


# ---------------------------------------------------------------- the patterns


def test_the_orchestrator_sources_are_found():
    assert {"turn.py", "planner.py", "maf_agent.py", "maf_write_flow.py", "maf_review_pack.py", "maf_write_steps.py"} <= set(SOURCES)


def test_an_agent_is_built_for_an_open_question_and_nowhere_else():
    assert {f for f, _ in callers("Agent")} == set(AGENTS), "an Agent is for open Q&A: add a registry entry with a reason, or use a Workflow"
    assert callers("build_agent") == {("planner.py", "Planner._with_agent")}
    assert {f for f, _ in callers("plan")} <= {"turn.py", "planner.py"}, "only the pipeline asks a planner to plan"


def test_a_workflow_is_built_for_a_fixed_sequence_or_a_confirmation_and_nowhere_else():
    assert {f for f, _ in callers("WorkflowBuilder")} == set(WORKFLOWS)
    subclasses = {f for f in SOURCES for _, n in walk(parse(f)) if isinstance(n, ast.ClassDef) and any(ast.unparse(b) == "Executor" for b in n.bases)}
    assert subclasses == {"maf_write_steps.py", "maf_review_pack.py"}, "an executor belongs to a registered workflow"
    users = {f for f in SOURCES if imported_members(f) & PRIMITIVES}
    assert users == WORKFLOW_MODULES, f"workflow primitives are used outside the registered workflows: {users ^ WORKFLOW_MODULES}"
    assert all(WORKFLOWS.values()) and all(AGENTS.values()), "every registry entry says why"


def test_no_workflow_reaches_a_model_and_no_open_question_starts_a_workflow():
    for name in WORKFLOW_MODULES:
        reached = {m for m in importers(MODEL_SIDE) if m == name}
        assert not reached, f"{name} imports the model side: a workflow is not open Q&A"
    started = importers({"app.core.maf_write_flow", "app.core.maf_write_steps", "app.core.maf_review_pack"})
    assert not started & OPEN_QA_MODULES, f"an open-question module starts a workflow: {started & OPEN_QA_MODULES}"
    assert started == {"turn.py", "maf_catalog_tools.py", "maf_write_flow.py"}, "a workflow is started by the pipeline, or by a prepare tool"


@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
def test_an_entry_point_is_called_only_from_where_it_is_allowed(entry):
    assert {f for f, _ in callers(entry)} <= ENTRY_POINTS[entry], f"{entry} is called from outside {sorted(ENTRY_POINTS[entry])}"


@pytest.mark.parametrize("link", sorted(CONSTRUCTORS))
def test_the_commit_chain_is_built_only_by_the_step_before_it(link):
    assert callers(link) <= CONSTRUCTORS[link], f"{link} is called from {sorted(callers(link) - CONSTRUCTORS[link])}"
    assert callers(link), "and the rule still describes a real call"


def test_the_only_tool_body_that_starts_the_write_workflow_is_the_prepare_body_chosen_for_a_preview_by_the_catalog():
    assert importers({"app.core.maf_write_flow.prepare_body"}) == {"maf_catalog_tools.py"}
    body = next(n for _, n in walk(parse("maf_catalog_tools.py")) if isinstance(n, ast.FunctionDef) and n.name == "body_for")
    assert "WRITE_PREPARE" in ast.unparse(body) and not callers("Commit") - CONSTRUCTORS["Commit"]


def test_no_sequence_of_tool_calls_stands_outside_an_executor_the_agent_or_a_named_degraded_planner():
    found = {(f, owner) for f in SOURCES for owner in tool_call_sequences(SOURCES[f].read_text(encoding="utf-8"))}
    assert found == set(SEQUENCES), f"a loose sequence of tool calls (use a Workflow, or the Agent): {sorted(found ^ set(SEQUENCES))}"
    assert all(SEQUENCES.values())


# ------------------------------------------------------- no executor computes


def scan_scope() -> dict[str, set[str] | None]:
    """File to the functions scanned (None for the whole file): the MAF layer, and the tool bodies elsewhere."""
    whole = {n: None for n in SOURCES if n.startswith("maf_") and n not in NOT_SCANNED}
    return {**whole, **FIGURE_FREE_FUNCTIONS}


def real_hits() -> list[tuple[str, str, str]]:
    return [
        (f, owner, statement) for f, only in scan_scope().items()
        for owner, _, _, statement in figure_computations(SOURCES[f].read_text(encoding="utf-8"), only)
    ]


def test_every_module_that_defines_an_executor_a_tool_or_tool_middleware_is_scanned_for_figures():
    def defines(name: str) -> bool:
        tree = parse(name)
        classes = [b for _, n in walk(tree) if isinstance(n, ast.ClassDef) for b in n.bases]
        return any(ast.unparse(b) in ("Executor", "FunctionMiddleware") for b in classes) or "FunctionTool" in imported_members(name)

    unscanned = {n for n in SOURCES if defines(n) and n not in scan_scope()}
    assert not unscanned, f"an executor or tool module is outside the figure scan: {sorted(unscanned)}"
    assert set(NOT_SCANNED) <= set(SOURCES) and all(NOT_SCANNED.values())


def test_no_executor_or_tool_body_computes_or_formats_a_figure():
    allowed = set(ARITHMETIC)
    unexpected = [hit for hit in real_hits() if hit not in allowed]
    assert not unexpected, "an executor or tool body computes or formats a number (figures come from the tools):\n  " + "\n  ".join(map(str, unexpected))


def test_every_allowed_arithmetic_statement_still_exists_and_says_why():
    assert set(ARITHMETIC) <= set(real_hits()), f"stale allowance: {sorted(set(ARITHMETIC) - set(real_hits()))}"
    assert all(ARITHMETIC.values())


# ------------------------------------------------------- the detector bites

SEEDED = {
    "multiplies an envelope value": "def f(reply):\n    return reply.body['facts']['credit'] * 2",
    "adds two values": "def f(a, b):\n    return a + b",
    "rounds": "def f(x):\n    return round(x, 2)",
    "sums rows": "def f(rows):\n    return sum(r['v'] for r in rows)",
    "takes a maximum": "def f(a, b):\n    return max(a, b)",
    "divides": "def f(a, b):\n    return a / b",
    "powers": "def f(a):\n    return a ** 2",
    "negates": "def f(a):\n    return -a",
    "increments a total": "def f(rows):\n    t = 0\n    for r in rows:\n        t += r['v']",
    "adds a conditional value": "def f(t, c, v):\n    t += v if c else 0",
    "parses a float": "def f(x):\n    return float(x['v'])",
    "builds a Decimal": "def f(x):\n    return Decimal(x)",
    "formats a number in an f-string": "def f(x):\n    return f'{x:,.2f}'",
    "formats with str.format": "def f(x):\n    return '{:.1f}'.format(x)",
    "formats with %": "def f(x):\n    return '%.2f' % x",
    "calls the format builtin": "def f(x):\n    return format(x, ',')",
    "imports maths": "import math\n",
    "imports statistics": "from statistics import mean\n",
}
CLEAN = {
    "compares": "def f(a, b):\n    return a >= b",
    "counts items": "def f(a):\n    return len(a)",
    "joins text": "def f(a):\n    return 'x' + a + '\\n'",
    "repeats text": "def f():\n    return '-' * 3",
    "slices": "def f(a):\n    return a[:12]",
    "literal arithmetic": "X = 2 * 3",
    "builds a container": "def f(a):\n    return [*a] + ['x']",
    "plain f-string": "def f(x):\n    return f'{x}'",
    "keeps a mapping": "def f(a):\n    return {'k': a}",
    "extends a list conditionally": "def f(runs, link):\n    runs += [link] if link else []",
}


@pytest.mark.parametrize("name", sorted(SEEDED))
def test_the_figure_detector_catches_a_seeded_violation(name):
    assert figure_computations(SEEDED[name]), f"the detector missed: {name}"


@pytest.mark.parametrize("name", sorted(CLEAN))
def test_the_figure_detector_leaves_ordinary_code_alone(name):
    assert not figure_computations(CLEAN[name]), f"a false positive on: {name}"


def test_a_violation_slipped_into_a_real_executor_is_caught_and_the_function_is_named():
    source = SOURCES["maf_write_steps.py"].read_text(encoding="utf-8")
    assert not [h for h in figure_computations(source) if (("maf_write_steps.py", h[0], h[3]) not in ARITHMETIC)]
    seeded = source.replace("self._c.prepared.reply = reply", "self._c.prepared.reply = reply\n        bump = reply.body['facts']['credit'] * 1.1", 1)
    hits = figure_computations(seeded)
    assert [(h[0], h[2]) for h in hits] == [("Prepare.prepare", "arithmetic")], hits


def test_a_violation_slipped_into_a_real_tool_body_is_caught_through_the_function_scope():
    source = SOURCES["tools.py"].read_text(encoding="utf-8")
    seeded = source.replace("return reply\n\n    async def forward", "return reply\n\n    async def forward", 1).replace(
        '"""The generated tools\' one outbound call: `spec`\'s tool, as the acting person, answered untouched."""',
        '"""x"""\n        total = round(args["n"], 2)', 1)
    only = FIGURE_FREE_FUNCTIONS["tools.py"]
    assert not figure_computations(source, only), "the real tool body is clean"
    assert [h[0] for h in figure_computations(seeded, only)] == ["ToolRunner.forward"]


SEQUENCE_SEEDED = {
    "two tools in a row": "async def f(runner):\n    await runner.run('a', {})\n    await runner.run('b', {})",
    "a tool in a loop": "async def f(runner, names):\n    for n in names:\n        await runner.run(n, {})",
    "two gateway calls": "async def f(g):\n    await g.call_tool('a')\n    await g.call_tool('b')",
    "a tool in a comprehension": "async def f(turn, names):\n    return [await turn.run(n) for n in names]",
}


@pytest.mark.parametrize("name", sorted(SEQUENCE_SEEDED))
def test_the_sequence_detector_catches_a_loose_sequence(name):
    assert tool_call_sequences(SEQUENCE_SEEDED[name]) == {"f"}


def test_the_sequence_detector_leaves_one_call_and_unrelated_runs_alone():
    assert not tool_call_sequences("async def f(runner):\n    return await runner.run('a', {})")
    assert not tool_call_sequences("async def f(flow, agent):\n    await flow.run(1)\n    await agent.run(2)")
    assert not tool_call_sequences("async def f(runner):\n    async def g():\n        await runner.run('a')\n    await runner.run('b')")
