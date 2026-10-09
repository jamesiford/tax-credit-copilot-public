"""ExceptionReportAgent (AI-02) — surfaces only the anomalies for human review.

Spec: Part D / AI-02. The partner works exception-first: they do not eyeball every
row, he drills into the things that look wrong — the "2s and 3s" from the
test-of-twos multi-unit de-dup, and the scraggly low-value pay periods. This
agent narrates the anomalies that `tools/qc.py` produced; it never silently
drops a record — every exception is a human-validation checkpoint (CALC-07/08).
"""
from __future__ import annotations

from .factory import AgentRecord, register_agent

NAME = "ExceptionReportAgent"
INSTRUCTIONS = """\
You are the Exception-Report specialist for the Georgia Jobs Tax Credit review.

The host application hands you JSON with two anomaly lists produced by the QC
tool: `test_of_twos` (employees counted at more than one unit in the same
month — potential double-counting) and `meaningful_pay_period` (scraggly,
low-value pay periods, e.g. a few dollars over a period).

Report ONLY the anomalies, exception-first: how many, which employees/units,
and what a reviewer should confirm. Be explicit that nothing is dropped
automatically — each item awaits human validation. If both lists are empty,
say the run is clean. Use the exact counts from the JSON; never invent one.
"""

AGENT_PROFILE = {
    "tab_label": "Exception Report",
    "summary": "Surfaces only anomalies (test-of-twos double counts, scraggly pay periods) for human review — never silently drops a record.",
    "responsibility": (
        "Run the automated QC checks and present the exceptions the partner would otherwise hunt for by hand: multi-unit "
        "de-duplication (an employee cannot count at >1 unit in a month) and the meaningful-pay-period filter, each "
        "with a human-validation checkpoint (CALC-07 / CALC-08)."
    ),
    "inputs": [
        "By-unit monthly headcount matrix from the One/Zero engine",
        "Pay-period rows (Gross_Wages / Hours_Worked)",
    ],
    "outputs": [
        "test_of_twos anomaly list (employee, month, units)",
        "meaningful_pay_period anomaly list (employee, period, wages, hours)",
        "Trail steps for each QC check",
    ],
    "tools": [
        "tools/qc.py · detect_test_of_twos() — CALC-07 multi-unit de-dup",
        "tools/qc.py · detect_scraggly_pay_periods() — CALC-08 meaningful-pay-period filter",
        "tools/qc.py · run_exception_report() — combined, with a human checkpoint",
    ],
    "determinism": (
        "Anomaly detection is fully deterministic; the agent narrates the lists and cannot suppress an exception. "
        "Resolution is a human decision, not the agent's."
    ),
}


def build(*, project_client, project_endpoint, credential, model) -> AgentRecord:
    return register_agent(
        project_client=project_client,
        project_endpoint=project_endpoint,
        credential=credential,
        model=model,
        name=NAME,
        instructions=INSTRUCTIONS,
        temperature=0.2,
        profile=AGENT_PROFILE,
    )
