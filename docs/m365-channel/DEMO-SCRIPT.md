# Demo script and manual test checklist

A step-by-step demo of the channel in **Teams**, **Microsoft 365 Copilot Chat** and **Copilot Cowork**,
and the checklist the owner runs after the live deployment. It uses only the synthetic clients in this
repository's data:

| Client | Where it comes from |
| --- | --- |
| **Cascade Retail Partners** (account 2001) | `backend/data/source/synth.py`: steady growth, calendar fiscal year, three states |
| **Northwind Care Systems** (2002) | same |
| **Ironbridge Logistics** (2003) | same |
| **Halloway Foods** (2004) | same: a July-to-June filer whose headcount fell |

**Figures are not in this script on purpose.** They come from the engine, and what the screen shows is whatever
the run holds. Where this says "compare", open the named portal page at the same scope and read the same number
off it. If they differ, that is a defect to report, not a rounding to explain.

## Say these three things first

1. **The identity on Teams and Copilot Chat is asserted by the channel.** The orchestrator tells the platform
   who is asking; it is not a token of that person's own. Every audit row says `channel-asserted`. Cowork uses the
   person's own token (`delegated`).
2. **Cowork's wording relies on its skills and on `verify_figures`.** On Teams and Copilot Chat code assembles the
   reply and a figure it cannot trace is dropped. In Cowork the model writes the document, and the figure check is
   a step it is told to run. A wrong figure is *caught if the author checks*.
3. **Everything here is synthetic data**, and the demo posture leaves the gateway and the Foundry data plane
   reachable from the internet (authenticated). That is acceptable only because there is no real data.

## Before you start

| | |
| --- | --- |
| Posture | `terraform -chdir=infra output network_posture` reads `demo-public-foundry` while you deploy and publish; set it back afterwards ([RUNBOOK §13.5](../architecture/RUNBOOK.md)) |
| A **writer** and a **reader** | Two people (or two test accounts). Add the writer: `python scripts/channel-writers.py add <oid> --name "<display name>"`. The reader is anyone else who can sign in |
| The portal open at the same scope | `/` for the book, `/c/<clientId>` for a client. Use the writer's browser |
| A terminal ready for the audit | `python scripts/channel-audit.py --user <oid>` (set `CHANNEL_STORE`/Warehouse settings as for the API) |
| The plugin installed for Cowork | [COWORK-SETUP](COWORK-SETUP.md): *Shared with me*, or listed by an admin |

## Part 1: Teams

Open a chat with the published agent as the **writer**. Type each prompt as written.

### 1.1 Who to call (no client needed)

> **Who should we call first?**

*Expect:* a ranked table (client, reason, programme, tax year, identified credit, jobs margin), a sentence at most
of commentary, the standing disclaimer, and a provenance footer. The reason is one of the page's words
(*Identified*, *On the line*, *Declining*, *Exposed*, *Not assessed*, *Nothing found*), never a score.
*Compare:* the portfolio page `/`, same order, same identified figures. The ranking does not depend on a year.

### 1.2 A client's position

> **Brief me on Northwind**

*Expect:* the client's cells by reason, with the identified credit per programme-year. Then ask:

> **How has Cascade trended since its base year?**

*Expect:* a year-by-year table and a sentence saying whether the client has been eligible since its base year. If
the run holds nothing after the base year it says so rather than answering "no".
*Compare:* the client page `/c/2001`, the location grid's roll-up.

### 1.3 The credit for a year, under both certified methods

> **What is Cascade's credit for 2023?**

*Expect:* **both** certified methods, each labelled, because the statute does not choose one; the figures are the
engine's. Then name one: **Cascade's credit for 2023 under Pay Period** shows only that method.
*Compare:* the client page at `?year=2023&method=pay_period` (and `min_max`).

### 1.4 It asks rather than guesses

> **What is the credit for 2023?**

*Expect:* a question: which client? Then **Compare Cascade and Northwind for 2023** and answer with a number from
its numbered list. A year you did not say is also asked for: **What is Cascade's credit?**

### 1.5 A year with no authored rule pack

> **What is Cascade's credit for 2019?**

*Expect:* the platform **declines by name** (no authored rule pack for that year). It does not estimate from a
neighbouring year. This is the audit-defensibility story: a missing ruleset is a real gap in coverage.

### 1.6 Jobs that could fall out, other programmes, a what-if, the working

> **Which of Cascade's counted jobs could fall out in 2023?**
> **What else might Ironbridge qualify for?**
> **What if Cascade hired 2 people at site GA_GA-007 in 2025?**
> **Walk me through Cascade's 2023 calculation**

*Expect:* a near-the-floor list that describes a *completed* year (it does not predict anyone will leave); other
programmes from the rule-pack library, as possibilities; the what-if's figures labelled as the engine's (an open
year is a run-rate estimate and says so); and the calculation trail, step by step, with its evidence hash.
The what-if's size (2) and the year are *yours*: if you leave out the number it asks how many.

### 1.7 A change, with the confirm step

> **Mark Cascade's GA_JTC engagement as in scope**

*Expect:* a **preview** of exactly what would change (the field, now and after), the sentence "Reply **confirm** to
apply this change, or **cancel** to drop it", and no token in the text. Then:

> **confirm**

*Expect:* what changed, once. Try the variants live:

| You type | What happens |
| --- | --- |
| `confirm` again | Nothing to repeat: it was applied once |
| `please go ahead and confirm it` | A new question, **not** a confirmation |
| `cancel` | The pending change is dropped |
| any other question after the preview | The pending change is dropped, and the reply says so |

Show the finding and claim writes the same way, using a finding id the portal's Agent activity page lists for the
client you are demonstrating:

> **Accept finding <finding id> for Cascade in 2023**
> **Mark Cascade's GA_JTC claim for 2023 as proposed**

### 1.8 A reader cannot write

Sign in as the **reader** and repeat 1.7's first prompt. *Expect:* the reader is told at the **preview** that they
may read but not make changes, and nothing is written. Every read in 1.1 to 1.6 works.

### 1.9 The claim package

> **Send me the claim package for Cascade 2023** then **confirm**

*Expect:* the package is built after a confirmation, then a download link for **you only**, once, for fifteen
minutes. Open it: a workbook with Coverage, Locations, Installments, Provenance and Disclaimer sheets. Open the
link again: refused (used). Open it as someone else: refused.
*Compare:* the Evidence pack page in the portal.

## Part 2: Microsoft 365 Copilot Chat

Open Copilot Chat, pick the published agent from the agent list, and repeat 1.1, 1.3, 1.5 and 1.7. *Expect:* the
same replies; it is the same orchestrator. Point out the one difference you can see (the channel recorded in the
audit is `m365-copilot` rather than `teams`) and that **nothing about the replies' exactness depends on the
surface**.

## Part 3: Cowork

Open Cowork as the **writer** with the plugin installed. Say the caveat about wording again.

### 3.1 W1: the Monday book review

> **Run the Monday book review and build me a call plan.**

*Watch for:* the skill ranks the book (`book_rank`), reads each client (it resolves the name, then
`client_situation` and `client_trend`), finds the last contact in your mail, Teams and calendar (read-only, and
says what it found and did not find), builds an **Excel call plan** with the engine's figures copied verbatim, and
runs `verify_figures` before it hands the workbook over. Then it offers Outlook **drafts** (never sent) and a To Do
list for the clients you choose, and offers `engagement_set` for the ones you accept, **one at a time**, each with
its own preview and its own confirmation.
*Compare:* every figure in the workbook against the portfolio page.
*Try to break it:* edit one dollar figure in the workbook, paste the text back and ask it to verify. It rejects it.

### 3.2 W2: a client credit review pack

> **Prepare a credit review pack for Cascade Retail Partners, tax year 2023, Georgia.**

*Watch for:* it asks you to **confirm** the client (the resolver always asks when nothing is selected); reads
eligibility, trend, jobs at risk and other programmes; asks you for a **decision on each open finding** with its
evidence, and records each only after you say yes; moves the claim to `proposed` only if you ask; authors a Word
briefing and a deck of at most six slides from tool output only, with the disclaimer and a provenance footer
(run, rule pack, assumptions, trail hash); builds the package and gives the link; verifies every artifact; and
offers a calendar hold with no figures in it.
*Compare:* the briefing's figures against the client page; the footer's trail hash against the calculation walk in
the Evidence pack.

### 3.3 A reader in Cowork

Repeat 3.1 as the reader. *Expect:* every read works; the engagement commit is refused as **not authorised**, the
skill says so and stops that part, and the workbook and drafts are unaffected.

## Part 4: The per-user audit

Right after the demo, as the operator:

```pwsh
python scripts/channel-audit.py --user <writer oid>
python scripts/channel-audit.py --user <reader oid> --tool engagement_set_prepare
```

*Expect a timeline, newest first, one line per request:*

```
<time>  ok       write_commit   engagement_set_commit   client 2001
<time>  ok       write_prepare  engagement_set_prepare  client 2001
<time>  ok       read           client_trend            client 2001
<time>  ok       read           book_rank               no client
```

and, for the reader, a `refused` line for the preview. A request with no end shows `PENDING`. The same data, with
the channel, the identity assurance (`channel-asserted` for Teams and Copilot Chat, `delegated` for Cowork) and the
`confirmation_ref` linking each commit to the preview it confirmed, is `GET /api/audit/channel?user_oid=<oid>` with
an operator's token. Point out that the writer's rows say `teams` and `cowork`, and that the reader's refusal is
in the trail.

## Manual test checklist (after the live deployment)

Run it once per surface. Tick, date and initial each line; record a failure with the exact prompt and the reply.

| # | Check | Teams | Copilot Chat | Cowork |
| --- | --- | --- | --- | --- |
| 1 | The agent or plugin appears for the writer and for the reader | ☐ | ☐ | ☐ |
| 2 | Who to call: ranked, in the portal's order, no client needed | ☐ | ☐ | ☐ |
| 3 | A client's position and trend match the portal page | ☐ | ☐ | ☐ |
| 4 | Credit for a year: both methods labelled, figures match the portal | ☐ | ☐ | ☐ |
| 5 | A missing client or year is asked for, never defaulted | ☐ | ☐ | ☐ |
| 6 | A year with no authored rule pack is declined by name | ☐ | ☐ | ☐ |
| 7 | A what-if's size is the reader's; a missing size is asked for | ☐ | ☐ | ☐ |
| 8 | Prepare shows a preview and changes nothing (check the portal) | ☐ | ☐ | ☐ |
| 9 | Confirm applies the change once; a repeat does nothing | ☐ | ☐ | ☐ |
| 10 | Cancel, or any other message, drops the pending change | ☐ | ☐ | n/a (the skill's own confirmation) |
| 11 | A reader is refused at the preview or the commit; nothing is written | ☐ | ☐ | ☐ |
| 12 | The claim package link works once, for that person only | ☐ | ☐ | ☐ |
| 13 | A tampered figure is rejected by `verify_figures` | n/a | n/a | ☐ |
| 14 | The workbook, briefing and deck figures equal the portal's | n/a | n/a | ☐ |
| 15 | The audit shows the right person, channel and assurance for every call above | ☐ | ☐ | ☐ |
| 16 | The audit shows the reader's refusal as `refused` | ☐ | ☐ | ☐ |
| 17 | `network_posture` is read back to `private` after the demo | ☐ | | |
| 18 | The caveats were said: asserted identity, Cowork wording, synthetic data | ☐ | ☐ | ☐ |

Anything that fails is recorded in [STATUS.md](STATUS.md) under Blockers with the prompt, the reply and the
correlation id from the error body ([RUNBOOK §13](../architecture/RUNBOOK.md)).
