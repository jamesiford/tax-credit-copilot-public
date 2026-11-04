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
4. **Data handling in the sandbox.** The PoC reads an existing Fabric workspace that holds the five synthetic named
   clients and the reference dataset (shown in the app as "Reference Dataset Client", 10,236 employees). The owner's
   statement is that no personal data is housed there: employee identifiers are pseudonymous tokens, with no names,
   SSNs, emails or free text. That was checked read-only before the deployment (column names, row counts and the shape
   of a few values; nothing copied): no personal names, emails or phone numbers exist, and the tax-identifier and address
   columns hold obvious placeholder business values. The deployment is therefore classified `synthetic`. Do not point it
   at real payroll without the hardening plan.

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

### 1.6b Nuanced data questions (CH-17)

These go through the governed data tools (`data_catalog`, `data_query`) against a synthetic client, and each is checked live.
Ask them one at a time, about a minute apart is plenty now; each answer shows the engine's table with its source line.

> **How many employees were counted under Min-Max and under Pay Period at GA_GA-001 for Northwind Care Systems in 2025?**
> **Which jobs are at risk at Northwind Care Systems in 2025?**
> **How many Northwind Care Systems employees speak Spanish at home?**
> **Round the credit to the nearest thousand for Northwind Care Systems in 2025.**

*Expect:* the first returns both methods' counts at that location in a table and says the *difference* is not in it (it never
subtracts for you); the second gives the count and the jobs at risk for a completed year; the third is a polite, exact refusal
(the data has no such column; nothing is guessed); the fourth shows both methods' credits exactly and says the platform gives every
figure exactly as computed (no rounded figure, ever: a narration that rounds is withheld by the guard).
*Known weak spots, say so if asked:* "which month had the lowest headcount" (a twelve-month series: it shows the first half-year
and says the rest needs a second query) and "average weekly hours per employee by location" (no single fact holds it); both are in
[KNOWN-LIMITATIONS](KNOWN-LIMITATIONS.md). A follow-up that says "their" works inside one conversation ("And what is their trend?").

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

*Watch for:* it takes the client from the name you gave without asking you to confirm it (an exact name
resolves; a partial or ambiguous one is asked back as a numbered list); reads
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

Anything that fails is recorded in [REMEDIATION-STATUS.md](REMEDIATION-STATUS.md) under Blockers with the prompt, the reply and the
correlation id from the error body ([RUNBOOK §13](../architecture/RUNBOOK.md)).

## Appendix: the live sandbox, what only a person can do

Placeholders only here; the filled-in copy is the private deploy notes. Everything the automation could check
(gateway REST and MCP, the per-user audit, the writes, the certified figures) is in
[evidence/live-smoke-2026-11-03.md](../archive/evidence/live-smoke-2026-11-03.md). What follows needs a person in Teams or
Copilot, because nothing can send a message on a person's behalf.

1. **S2 / S1: Teams.** Open `<share link>`, add the agent, send `/whoami`. Expect: your object id (`<operator oid>`),
   a display name, assurance `channel-asserted`, and the source named. Paste the reply into the private notes. Then run
   `pwsh scripts/channel-smoke.ps1 -Since '<time just before you typed>'` and confirm the audit row shows the same id.
   If `/whoami` says it cannot tell who you are, that is the finding (see ORCHESTRATOR.md, `CHANNEL_IDENTITY_SOURCES`).
   If the share link does not open the agent, sideload the package azd generated (`channel_orchestrator/appPackage.zip`
   on the deploying machine, ignored by git): Teams, Apps, Manage your apps, Upload a custom app.
2. **Copilot Chat.** Find the agent under *Your agents*; run the three demo prompts (book, client brief, what-if).
   Compare the figures with the portal. A reply has one or two sentences of model commentary above the engine's tables (M-01 is fixed); the figures, tables and disclaimer are the engine's.
3. **Write flow.** "Move `<client>` TY`<year>` to proposed", read the preview, reply `confirm`. Check the row in the portal
   and the preview and commit pair in the audit. Try the same as a non-writer account if you have one.
4. **Guard.** Run `/whoami` after a few turns and confirm narration-audit rows exist when a model took part (it does not
   in the sandbox it does, so expect a 
arrate row per turn). There is no flag that forces a bad narration; skip the blocks-only check.
5. **Cowork (S5).** Register the OAuth client in the Teams Developer Portal for the gateway scope
   ([COWORK-SETUP](COWORK-SETUP.md)), put its registration id in `overlays/<name>/cowork.config.json`, rebuild with
   `python scripts/build-cowork-plugin.py --config overlays/<name>/cowork.config.json --strict`, install through
   *Shared with me*, run W1 and W2, then show the per-user audit.
6. Report back anything that differs from these documents.

### Retry in Teams (after the CH-14 fix), exactly

> **Superseded by the CH-17 list below for the icon and the package.** Kept for the diagnostics.

1. Use **Teams on the web in an InPrivate window**. Open the app from *Your agents* (or the share link). If you installed **either** app package by sideloading, remove it first and
   keep exactly **one** install: the publish package (`publish-appPackage-v1.0.3.zip`) and azd's sideload package share one app id and one bot id.
2. If the agent still shows as delivered with no reply, re-upload the package as a **new version** (the publish package is manifest 1.0.3 as published; the service stamps the download one patch higher) as an admin
   (Teams admin center, Manage apps, Upload new app), check the app's status is **Allowed**, then refresh the client.
3. Send `/whoami`. Expect JSON with `identity.resolved: true`, your object id, a source (`original-subject`, `platform` or `agent-user-id`), and under
   `signals.agent_user_id` its `kind` (`guid`) and `equals_an_oid_signal`. Paste it into the private notes.
4. Send `Which of our clients is closest to a threshold and what should I say if I call them?`. Expect a sentence or two, then the ranked table and the disclaimer.
5. Run `pwsh scripts/channel-smoke.ps1 -Since '<UTC time just before you typed>'`; the audit rows must show `channel=teams`, `identity_assurance=channel-asserted`, your id and
   a `narrate` row with `guard=pass`.

### Retry after CH-17 (agent version 20, app 1.0.3): in this order

What changed since the last retry: the agent has a new **icon** (published as 1.0.3), the display name and UPN are resolved in the
audit, the data tools answer nuanced questions, and the Cowork package is **v2**. The agent is **version 20** and the checks are green.

1. **Teams on the web, InPrivate window.** Remove the old app first (Apps, Manage your apps, the agent, Remove), then add
   `publish-appPackage-v1.0.3.zip` (or the share link): **one install only**. The new icon shows only after the old app is gone.
2. Send `/whoami`. Expect `version: 20`, `identity.resolved: true`, source `agent-user-id`. The display name there still reads
   "(name not provided)" (the agent sees no name; the audit has it, step 6).
3. Ask the whole-book question ("Who should we call first and why?"), a client brief, then "their" in the same chat.
4. Ask the nuanced questions of 1.6b, one at a time. If a reply says the language model is unavailable, wait a minute and ask again.
5. Try a what-if and a write with `confirm` (1.6, 1.7), then move the row back.
6. Run `pwsh scripts/channel-smoke.ps1 -Since '<UTC time before step 3>'`: `channel=teams`, your display name and UPN on every row, `narrate` rows.
7. **Copilot Chat:** find the agent under *Your agents* and run the same three prompts.
8. **Cowork:** upload `tcc-cowork-plugin-registered-v2.zip` (Sources and Skills, Plugins; or `atk install --file-path <zip> --scope Personal`),
   sign in when asked, run W1 and W2 (3.1, 3.2), then show the audit. If the first sign-in fails with an invalid-scope error,
   remove `offline_access` from the registration's scope.
9. When finished, switch the diagnostics off ([DEMO-CLEANUP](DEMO-CLEANUP.md)).

### Retry after RM-16 (agent version 21): before anything else

The remediation work (small-group suppression, the fail-closed Cowork rule, MAF tools and middleware, the write and review-pack Workflows, the
framework's chat client) is deployed as agent **version 21**, but its data checks have not run live (the shared Fabric capacity was suspended;
[evidence/live-remediation-2026-11-04.md](evidence/live-remediation-2026-11-04.md)). In this order:

1. **Resume the shared Fabric capacity** (owner action) and wait a few minutes for the API to warm.
2. Run the checklist at the end of the evidence file: invariants, `/whoami` (expect `version: 21`), the gateway smoke, then the twelve questions
   (the ten of the CH-17 retest, plus a client review pack and a prepared write you do not confirm).
3. Compare with [evidence/live-final-2026-11-03.md](../archive/evidence/live-final-2026-11-03.md). Any regression: `agent-endpoint.ps1 -Action Pin -Version 20`.
4. Then the retest above (CH-17) in Teams and Cowork. Small groups: a non-writer asking for an average over fewer than five people gets the group left out and
   counted; a writer (you) is exempt, so the demo shows the exempt view.

### Troubleshooting: the agent does not answer

| What you see | What it means | What to do |
| --- | --- | --- |
| Delivered, no reply; Bot Service shows only 200 | The platform could not hand the message to the container. Seen once: `activity` declared as a container protocol, so Teams messages went to `/activity/messages` (404) | `pwsh` the agent definition (`GET /agents/<name>`): `definition.protocol_versions` must be `responses` only, `agent_endpoint.protocols` `activity, responses`, schemes `Entra, BotServiceRbac`. Then `azd ai agent monitor <name> --session-id <id> --type console` and look for `POST /activity/messages ... 404` |
| "I couldn't answer that: the audit trail is unavailable; nothing was done." to every question | The Warehouse is unreachable. Seen on 4 November: the shared Fabric capacity was suspended (every tool call 503) | `az resource show` on the capacity (`Paused`?); the owner resumes it ([OPERATIONS](OPERATIONS.md)) |
| "I can't tell who you are" | No identity signal carried an object id | `/whoami`: read `signals` and `agent_user_id`; see ORCHESTRATOR.md, Identity |
| A reply with tables but "the language model is unavailable" | The model call failed (it was M-01) | `/netcheck` then `/modelprobe`: a name that does not resolve is the DNS finding in D-101 |
| "You cannot send messages to this bot", or delivered but nothing reaches it | Teams-side install state | Re-upload as a new version, refresh, check Allowed in the admin center ([KNOWN-LIMITATIONS](KNOWN-LIMITATIONS.md)) |
