"""The coding standards, as a ratchet over measured code. [AI-08]

Two halves. The first runs the real measurement over the real source tree and fails
when it is worse than the baseline — or better, until the baseline is tightened.
The second proves the measurement bites: a ratchet nobody has seen fail is one nobody
knows works, so each rule is shown firing on a crafted example.
"""
from __future__ import annotations

import textwrap

from tools.code_standards import baseline as ratchet
from tools.code_standards.duplicates import duplicate_findings
from tools.code_standards.metrics import LIMITS, complexity, measure

import ast


# --- the ratchet over the real tree --------------------------------------------------

def test_the_code_is_no_worse_than_the_baseline_and_the_baseline_is_as_tight_as_the_code():
    verdict = ratchet.compare(ratchet.current_findings(), ratchet.load_baseline())
    problems = [*(f"NEW      {r}" for r in verdict.new), *(f"WORSE    {r}" for r in verdict.worse),
                *(f"TIGHTEN  {r}" for r in verdict.improved)]
    assert verdict.ok, (
        "coding standards ratchet failed — fix the code, or after an improvement run "
        "`python scripts/code-standards.py --update`:\n  " + "\n  ".join(problems[:40])
    )


def test_the_baseline_records_the_limits_it_was_measured_against():
    import json

    assert json.loads(ratchet.BASELINE_PATH.read_text(encoding="utf-8"))["limits"] == LIMITS


def test_the_new_ai_layer_has_no_baselined_violations_in_size_or_shape():
    """The code written for the AI platform meets the standards outright; legacy does not get a vote here."""
    clean_roots = ("application/ai/", "infrastructure/ai/", "api/chat/", "domain/ai", "tools/code_standards/")
    shaped = ("module-lines", "class-lines", "function-lines", "complexity", "args", "bare-except")
    allowed = {  # pipelines moved here from the old single module, still over limit; tracked in CODE-STANDARDS.md
        "complexity|api/chat/dispatch.py::_dispatch", "function-lines|api/chat/dispatch.py::_dispatch",
        "complexity|api/chat/pipelines_core.py::_pipeline_eligibility", "function-lines|api/chat/pipelines_core.py::_pipeline_eligibility",
        "function-lines|api/chat/pipelines_core.py::_pipeline_portfolio", "function-lines|api/chat/pipelines_whatif.py::_pipeline_simulate",
        "complexity|api/chat/scope.py::_detect_state",
    }
    offenders = [k for k in ratchet.load_baseline()
                 if k.split("|", 1)[0] in shaped and k.split("|", 1)[1].startswith(clean_roots) and k not in allowed]
    assert not offenders, offenders


# --- the measurement bites -----------------------------------------------------------

def find(source: str, path: str = "x.py"):
    return {f.key.split("|", 1)[0]: f.value for f in measure(path, textwrap.dedent(source))}


def test_a_long_module_is_flagged():
    assert find('"""d"""\n' + "x = 1\n" * 260)["module-lines"] == 261


def test_a_long_function_is_flagged_with_its_length():
    body = "\n".join(f"    a{i} = {i}" for i in range(45))
    assert find(f'"""d"""\ndef big():\n    """why"""\n{body}\n')["function-lines"] == 47


def test_a_complex_function_is_flagged():
    branches = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(11))
    assert find(f'"""d"""\ndef f(x):\n    """why"""\n{branches}\n    return 0\n')["complexity"] == 12


def test_complexity_counts_each_decision_once_and_ignores_nested_functions():
    tree = ast.parse("def f(a, b):\n    if a and b or a:\n        pass\n    def g():\n        if a:\n            pass\n    return [x for x in a if x]\n")
    assert complexity(tree.body[0]) == 1 + 1 + 2 + 2


def test_too_many_arguments_are_flagged_and_self_is_not_counted():
    assert "args" not in find('"""d"""\nclass A:\n    """d"""\n    def m(self, a, b, c, d, e, f, g):\n        return 1\n')
    assert find('"""d"""\ndef f(a, b, c, d, e, f, g, h):\n    return 1\n')["args"] == 8


def test_a_bare_except_is_flagged():
    assert find('"""d"""\ndef f():\n    try:\n        pass\n    except:\n        pass\n')["bare-except"] == 1


def test_missing_docstrings_are_flagged_where_a_reader_needs_them():
    found = find("class Public:\n    pass\n\nclass _Private:\n    pass\n")
    assert found["docstring-module"] == 1 and found["docstring-class"] == 1
    long_public = "\n".join(f"    a{i} = {i}" for i in range(16))
    assert "docstring-function" in find(f'"""d"""\ndef f():\n{long_public}\n')
    assert "docstring-function" not in find(f'"""d"""\ndef _f():\n{long_public}\n')


def test_a_compliant_file_has_no_findings():
    assert find('"""Why this exists."""\n\n\ndef add(a, b):\n    """Sum."""\n    return a + b\n') == {}


def test_identical_function_bodies_in_two_files_are_a_duplicate():
    body = "\n".join(f"    v{i} = compute({i})" for i in range(9)) + "\n    return v0"
    one = f'"""d"""\ndef alpha(x):\n    """a"""\n{body}\n'
    two = f'"""d"""\ndef beta(x):\n    """b"""\n{body}\n'
    [dup] = duplicate_findings({"a.py": one, "b.py": two})
    assert dup.key.startswith("duplicate|") and dup.value == 2
    assert duplicate_findings({"a.py": one}) == []


def test_a_short_body_is_not_reported_as_a_duplicate():
    tiny = '"""d"""\ndef f():\n    return 1\n'
    assert duplicate_findings({"a.py": tiny, "b.py": tiny}) == []


# --- the ratchet's own rules ---------------------------------------------------------

def test_a_new_violation_fails():
    assert ratchet.compare({"function-lines|a.py::f": 50}, {}).new == ("function-lines|a.py::f = 50",)


def test_a_worse_violation_fails():
    verdict = ratchet.compare({"function-lines|a.py::f": 60}, {"function-lines|a.py::f": 50})
    assert verdict.worse and not verdict.ok


def test_a_better_or_fixed_violation_fails_until_the_baseline_is_tightened():
    assert ratchet.compare({"function-lines|a.py::f": 45}, {"function-lines|a.py::f": 50}).improved
    assert ratchet.compare({}, {"function-lines|a.py::f": 50}).improved


def test_an_unchanged_violation_passes():
    assert ratchet.compare({"complexity|a.py::f": 12}, {"complexity|a.py::f": 12}).ok


def test_moving_a_function_to_another_file_unchanged_is_not_a_new_violation():
    verdict = ratchet.compare({"complexity|new.py::f": 12}, {"complexity|old.py::f": 12})
    assert verdict.ok, verdict


def test_moving_a_function_and_making_it_worse_still_fails():
    assert not ratchet.compare({"complexity|new.py::f": 14}, {"complexity|old.py::f": 12}).ok


def test_a_moved_name_does_not_launder_a_different_rule_or_a_module_level_violation():
    assert not ratchet.compare({"args|new.py::f": 9}, {"complexity|old.py::f": 12}).ok
    assert not ratchet.compare({"module-lines|new.py": 300}, {"module-lines|old.py": 300}).ok
