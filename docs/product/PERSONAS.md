# Persona matrix — [J1] UX-01

**Story:** UX-01 — *"the prototype to support distinct views for at least Tax
Director, Tax Analyst, and one operational persona, so that each user sees only
the data and controls relevant to their role."*

**Acceptance criterion satisfied here:** *"A documented persona matrix is
produced before implementation."* This document is that matrix and is the
**contract** the frontend gating in `frontend/src/App.jsx` implements. If the
code and this table disagree, the code is wrong.

Persona is selectable at session level via the top-bar persona selector
(`activePersona` state in `App.jsx`). Production would assign it by identity
(Entra group) instead of a free selector.

> **Iteration note (ROADMAP-V · July 9).** Personas are **unchanged** this
> iteration. The July 9 work — the **Min Max ≥ Pay Period (1/0)** calc invariant
> and the **statute-grounded Tennessee** rule pack + cited rulebook — is
> role-agnostic. When Tennessee is scoped into the client UI, it inherits this
> same persona matrix unchanged.

## Personas

| Persona | Who | Mental model |
|---|---|---|
| **Tax Director** (default) | Maria Chen — runs eligibility calcs, files credits | Full control: monitor, plan, defend, configure, bill |
| **Tax Analyst** | Works per-employee under the Director | Does the per-employee / per-unit eligibility work; no commercial or admin surfaces |
| **Operational** | Ops / site manager consuming monitoring | Read-only situational awareness, **scoped to one site** ([O1] UX-05): sees Overview, Alerts, and the Headcount **Employees** tab for its own location only — a store-A manager cannot see store-B payroll |
| **Workforce Consultant** *(Partner Internal — [M0] ROADMAP-III)* | The partner's consultant working the whole book | A level UP from any one company: the **state-level Georgia opportunity book** ("who should we approach?"). Internal to the partner only; drills down into the company-level surfaces |

> **[M0] Internal vs. client POV.** The first three personas are **client-side**
> roles inside a single company (MeridianCore). The **Workforce Consultant** is
> an **internal partner** persona whose home POV is the cross-company
> **Opportunity Mining** view — a level above the single-company portal. It is
> the **only** persona that sees Opportunity Mining; no client persona does.
> Consistent with COPILOT-SCOPE.md's internal-only posture.

## View access matrix

> **This matrix is aspirational and its route ids are stale.** Persona filtering
> is not implemented — `NAV` in `frontend/src/App.jsx` is not filtered by
> anything, and no view listed below still exists under these ids. The shell now
> runs twelve views across five sections (What is it worth · Are we on track ·
> What needs a decision · What would change it · Prove it), pinned by
> `test_the_navigation_is_a_decided_set` in `App.test.jsx`. Read the code for
> what ships; read this for the access model still to be built.

Legend: ✅ visible · ⛔ hidden

| Nav section | View (route id) | Tax Director | Tax Analyst | Operational | Workforce Consultant *(internal)* |
|---|---|:--:|:--:|:--:|:--:|
| Monitor | Overview (`overview`) | ✅ | ✅ | ✅ | ✅ |
| Monitor | Data Ingestion (`ingestion`) | ✅ | ✅ | ⛔ | ✅ |
| Monitor | Alerts (`alerts`) | ✅ | ✅ | ✅ | ⛔ |
| Eligibility | Headcount — Sites + Employees (`headcount`) | ✅ | ✅ | ✅ *(scoped [O1])* | ✅ |
| Eligibility | Eligibility Validation (`simulator`) | ✅ | ✅ | ⛔ | ✅ |
| Credits | GJTC Capture & Filing (`portfolio`) | ✅ | ✅ | ⛔ | ✅ |
| Credits | **Opportunity Mining (`opportunity`)** *[M4]* | ⛔ | ⛔ | ⛔ | ✅ **(home)** |
| Defend | Evidence Packs (`evidence`) | ✅ | ✅ | ⛔ | ✅ |
| Defend | Audit & Compliance (`audit`) | ✅ | ✅ | ⛔ | ✅ |
| Defend | Rule Library (`rules`) | ✅ | ✅ | ⛔ | ✅ |
| Defend | Agent Workbench (`agents`) | ✅ | ✅ | ⛔ | ✅ |
| Configure | Value & Billing (`billing`) | ✅ | ⛔ | ⛔ | ⛔ |
| Configure | Settings (`settings`) | ✅ | ⛔ | ⛔ | ⛔ |

> **Data Ingestion** (source → canonical → QC) and **GJTC Capture & Filing**
> (capture report + IT-CA filing workflow) posture the human-in-the-loop
> validation/correction over agent-automated ingest, calc, and mapping. The
> standalone **Discovery** page was folded into **GJTC Capture & Filing** (its
> retroactive-scan layers now live there).

## Control / action gating

| Control | Tax Director | Tax Analyst | Operational | Workforce Consultant *(internal)* |
|---|:--:|:--:|:--:|:--:|
| Ask Copilot drawer | ✅ | ✅ | ✅ | ✅ |
| Add manual claim (modal) | ✅ | ✅ | ⛔ | ⛔ |
| Run What-If simulation | ✅ | ✅ | ⛔ | ✅ |
| Rule-pack verify / sign-off | ✅ | ⛔ | ⛔ | ⛔ |
| Change commercial model / fee (Settings) | ✅ | ⛔ | ⛔ | ⛔ |
| Change fiscal-year / client overrides (Settings) | ✅ | ⛔ | ⛔ | ⛔ |
| Acknowledge / resolve alerts | ✅ | ✅ | ✅ | ⛔ |

## Implementation notes

- `PERSONAS` constant in `App.jsx` mirrors this table (`id`, `label`,
  `allowedViews`, `allowedActions`).
- `NAV` is filtered by `allowedViews` for the active persona before render.
- If the active view becomes hidden after a persona switch, the app falls back
  to `overview` (always visible to every persona).
- Copilot is internal-only regardless of persona — see COPILOT-SCOPE.md
  ([K3] UX-04). Persona gates *which partner-internal user* sees what; it does
  **not** open the copilot to clients.

*Internal prototype. Synthetic data only.*
