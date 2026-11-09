# How AI was used to build this

The brief asks to see the prompts and the AI harness. This file records how the work was split between me and an AI assistant (Claude), what was checked, and where the result differs from the plan.

## 1. Workflow

| Step | Who | Output |
|---|---|---|
| Read the brief, data and policy; profile the data for traps | AI, reviewed by me | Findings in `plan.md` §3 (3 currencies, FX moving approval bands, 21/25/29/2 control flags, data gaps) |
| Decide architecture, build order, API contract, stretch goal | AI proposed, I decided | `docs/plan.md` |
| Decide the eval set's status (the brief allows one stretch goal) | **Me**: keep guardrails as the stretch goal; design the eval set but don't build it | `plan.md` §12–13 |
| System design diagram | AI | `docs/architecture.png` |
| Generate the code from the plan | AI | `backend/`, `frontend/` |
| Review, run and adjust | Me | See sections 3 and 4 |

## 2. The prompts I used (verbatim or near-verbatim)

1. **Planning:** "You are the lead engineer on a project: a finance spend intelligence
assistant (FastAPI backend, React frontend, and an LLM that answers questions about 2025
invoices and a procurement policy, showing the evidence behind every answer). Attached:
the brief and the data pack (invoices, vendor master, procurement policy). I'll use a
Claude API key, referred to as key_1 in the code.

We work in two phases. Phase 1 is planning only: do not write any code, and do not answer
the brief's example questions. Stop at the end of Phase 1 and wait for my approval.

## Phase 1: the plan

Before planning, read everything and profile the data. Look for anything that would make
a naive answer wrong: currencies and conversion, policy thresholds and how they apply to
the data, missing or blank fields, negative amounts, vendor statuses, and questions the
data cannot answer at all. Give counts and example invoice numbers for each finding.

Then write the plan in three parts.

### 1. What will be built
- The components (backend modules, LLM integration, frontend views) and how they connect,
  with a simple diagram.
- The API contract for POST /ask and GET /summary: fields, statuses and errors.
- How the LLM is used: what it decides, what code computes, how evidence is produced and
  checked, and what happens when the data can't answer.
- The stretch goal you recommend (the brief allows one) and what is deliberately left out.
- How it will be tested and evaluated.

### 2. Why
- For each major decision: the reason, tied to the brief, the policy or a data finding,
  and the main alternative you rejected, with the reason.
- Which risks the design addresses (wrong numbers, invented evidence, the wrong approver,
  silent assumptions) and how.
- Every assumption you are making, stated so I can confirm or change it.

### 3. In what order
- Numbered build steps. For each: what it delivers, how it will be checked, and a time
  estimate. The total must fit the time box.
- Riskiest and most valuable parts first. Get one question working end to end before
  widening.
- A cut line: what to drop, in order, if time runs short.

Finish with a short list of decisions I need to make, with your recommendation for each.
Write the plan as a document with headings and tables that a non-technical reviewer can
follow." (The brief, data pack and policy were attached.)

2. **The Build: (only after I approve/review the plan)** "Build in the approved order. After each step, run its checks and tell me in one line
  what is done.
- Keep to these rules throughout:
  - The LLM never computes numbers. Code does every sum, conversion and ranking.
  - Evidence (quoted clauses, result rows) is built by the server from the IDs the model
    returns, never written by the model.
  - Every calculation is tested against an independent reference that never imports the
    app.
  - The system prompt is a versioned file. The API contract is defined once in the
    backend and once in the frontend, and the two are kept in sync.
  - key_1 is read only from a git-ignored .env file and is never logged or returned.
- Write clean, well-structured code with plain-English docstrings and comments, so a
  non-technical reader can follow it.
- Write the README the brief asks for: what was built and left out, how to evaluate it,
  and what production would need.
- If something in the plan turns out to be wrong or impossible, stop and ask before
  changing it. Record every agreed change in docs/ai-workflow.md.
- Before you finish, run the tests and the frontend build. Then report what was built,
  what differs from the plan and why, and what you couldn't verify."

3. **Review against the policy:** I asked the AI to list places where the generated behaviour could be challenged against the policy or the brief. I went through its list, decided which points were real problems, and asked it to implement three of them (section 5).

The runtime prompt the app sends to Claude is a separate, reviewed file: `backend/app/llm/prompts/system_v2.md` (version `ask-v2`). `system_v1.md` is kept so the change can be compared.


## 3. What was checked while the code was generated

| Check | Result |
|---|---|
| Backend unit and flow tests (`pytest`: FX, approval bands, loader, policy parser, tools vs the independent reference, validators, the full question flow with a scripted fake Claude, summary, prompt) | All passing |
| UI in a real browser (Chromium via Playwright), against the real backend logic with a scripted Claude: summary panel, three answer types, evidence panel, contributing invoices, error card with Retry, narrow-screen layout | Works as designed |
| Frontend type check (strict TypeScript) | Passing |
| HTTP-layer tests (`tests/test_api.py`) | Written. They need FastAPI, which could not be installed in the generation sandbox, so **run `pytest` locally** to confirm |
| Real Claude calls | Not possible without the key. **Run the smoke questions** (`docs/smoke-questions.md`) |
| Official ECB rates | The ECB website was unreachable from the sandbox, so the AI shipped a labelled placeholder. I replaced it with the official ECB file (section 5, override 4) |

## 4. Differences from the plan, and why

- **FX file:** the plan's fallback (approximate monthly averages, labelled as a placeholder) was used at first, then replaced by the official ECB daily rates I downloaded (section 5, override 4). The download script and the placeholder were removed.
- **`app/assistant.py`:** added to keep the web layer (`main.py`) thin, so the whole question flow can be tested without a web server.
- **No agent framework, no vector database, no text-to-SQL:** as planned.
- **React 19** instead of 18: the current major version; nothing in the app depends on the difference.
- **How Claude is called:** the plan assumed a forced final tool call and temperature 0. The docs for the current default model (`claude-sonnet-5-5`) say it rejects forced `tool_choice` and sampling parameters with HTTP 400, and thinks by default. The orchestrator therefore uses `tool_choice: auto`, a **strict** `submit_answer` tool, no temperature, an `effort` setting, and passes thinking blocks back. A reply without a submit_answer call is sent back for correction.
- **Prompt v2:** the overrides in section 5 changed what Claude is told about spend and missing POs, so the prompt moved from `ask-v1` to `ask-v2` instead of being edited in place (CLAUDE.md rule 5). Every answer and audit-log entry records which version produced it.
- **Prompt v3:** a review of the deliverables found three places where the policy relies on information the data doesn't have: a reporting date for the §6.1 90-day rule, vendor status history for §4.1, and PO values for the §3 bands. One test answer had guessed a date for the 90-day rule. All three are now in the prompt's list of what the data does not contain, stated as assumptions when an answer relies on them, and ages are counted by `find_invoices` (`as_of`) only for a date the user gives.
- **Independent review:** a second AI pass reviewed the code that couldn't be run here (FastAPI layer, SDK error mapping). Its findings were fixed: CORS headers on 500 responses, the unknown-model error mapping, an overall deadline per question, no raw error text sent to the browser, and async `/health` and `/summary`.

## 5. Where I overrode or corrected the AI

I asked the AI to critique its own design against the policy, then decided which points to act on. Three changed the behaviour; a fourth, the exchange rates, came from my own review of the data. Each one is pinned by a test, so it can't quietly come back.

### Override 1: credit notes are no longer netted from spend (§6.1)

- **What the AI did.** The generated tools reported spend *net* of the two credit notes (INV-20029 and INV-20096, both Helix Consulting AG, EUR -78,090.06), with an assumption saying so. The summary headline was the net figure.
- **Why I changed it.** Policy §6.1 says a credit note must be matched to its original invoice before it is processed. The data has no link to the originals, so subtracting them treats unmatched documents as settled. That is the opposite of what an auditor wants. It also made Helix look smaller than it is in every ranking.
- **What it does now.** Spend counts invoices only (138, EUR 6,964,721.16). The credit notes are reported separately: in the totals, next to their vendor in every grouped table, and in a standard assumption on every spend answer. A net figure is given only when the user explicitly asks for one (`net_credit_notes=true`), and then the answer says matching can't be confirmed.
- **Files.** `tools/query_spend.py`, `tools/find_invoices.py`, `tools/__init__.py` (tool descriptions), `summary.py`, `schemas.py`, `evidence.py` (assumption text), `llm/prompts/system_v2.md`, `frontend/src/lib/types.ts`, `components/SummaryPanel.tsx`, `components/EvidencePanel.tsx`, `lib/format.ts`.
- **Tests.** `test_credit_notes_are_not_subtracted_by_default`, `test_credit_notes_are_shown_next_to_their_vendor`, `test_net_figure_only_on_request` (`test_tools.py`); `test_summary_totals_are_consistent`.

### Override 2: a missing PO is a breach only from EUR 1,000 (§2.1)

- **What the AI did.** Any invoice with an empty PO field was flagged as a §2 exception, whatever its amount.
- **Why I changed it.** §2.1 requires a PO only for purchases of EUR 1,000 or above. Flagging every blank field would overstate breaches and send people chasing invoices the policy allows. In this file all 21 invoices without a PO happen to be above EUR 1,000, so the count doesn't change. The rule does, and it would matter on the next file.
- **What it does now.** The loader keeps the raw fact (`missing_po_ref`) and adds `po_required` (EUR amount ≥ 1,000, after conversion) and `missing_required_po` (the actual breach). The summary, the tools, the prompt and the UI use the breach flag. The threshold lives in one constant next to the approval bands, and a test checks it against the policy text.
- **Files.** `policy/approval.py` (`PO_REQUIRED_FROM_EUR`), `data/loader.py`, `tools/filters.py`, `tools/find_invoices.py`, `summary.py`, `evidence.py`, `llm/prompts/system_v2.md`, `components/EvidencePanel.tsx`.
- **Tests.** `test_missing_po_below_eur_1000_is_not_a_breach` (removes the PO from a GBP 340.37 invoice and checks it isn't flagged), `test_credit_notes_never_require_a_po`, `test_po_threshold_matches_the_policy_text`.

### Override 3: an unverified figure turns "Answered" into "Partial"

- **What the AI did.** The numeric check added an "unverified figure" warning but left the status as the model set it. An answer containing an invented number could still show a green **Answered** badge.
- **Why I changed it.** People read the badge before the warnings. If a figure in the answer can't be traced to a query result, the policy or the question, the answer isn't complete, and the status should say so. Removed citations already downgraded the status; unverified figures now do the same.
- **What it does now.** `evidence.py` sets the status to `partial` whenever a figure fails the check, and keeps the warning that names it.
- **Files.** `evidence.py`.
- **Tests.** `test_invented_figure_is_flagged_and_downgrades_the_answer`, `test_a_grounded_answer_keeps_its_status` (`test_ask_flow.py`).

### Override 4: official ECB rates instead of the AI's placeholder (§5.1)

- **What the AI did.** It couldn't reach the ECB website, so it shipped approximate monthly average rates, labelled as a placeholder, plus a script to download the real ones. Every invoice in a month used the same rate: INV-20096 (20 October) was converted at the 1 October figure.
- **Why I changed it.** §5.1 asks for "the ECB reference rate on the invoice date". An approximation, however well labelled, isn't that, and a finance reviewer would question every EUR figure built on it.
- **What it does now.** I downloaded the official ECB rates for every business day of 2025 and added them as `data/ecb_eur_rates_2025.csv`, unchanged. The app reads that file as is (`FxTable.from_ecb_csv`), so its fingerprint matches the download. Weekend and holiday invoices use the previous business day's rate (16 invoices). I checked the file before using it: 255 business days, only the six ECB holidays missing, one cell written as `01.03` (read as 1.03). The placeholder, the download script and the "placeholder rates" warning in the UI were removed.
- **Effect.** Small, but now exact: spend moves by EUR 840 (to EUR 6,964,721.16), the credit notes to EUR -78,090.06, and no invoice changes approval band or PO requirement. The two FX examples still cross a band (INV-20065 is EUR 54,185.32, INV-20071 is EUR 49,127.10).
- **Files.** `data/ecb_eur_rates_2025.csv` (new), `data/fx.py`, `data/loader.py`, `summary.py`, `schemas.py`, `frontend/src/lib/types.ts`, `components/SummaryPanel.tsx`, `tests/reference.py`; removed `data/fx_rates_2025.csv` and `scripts/fetch_ecb_rates.py`.
- **Tests.** `test_invoice_uses_the_ecb_rate_of_its_own_date` (INV-20096 at 1.1655), `test_weekends_and_holidays_use_the_previous_business_day`, `test_ecb_file_is_read_as_downloaded` (`test_fx.py`). The test that checked a grounded answer had the Spain total written into it; it now reads the figure from the tool, so it holds whatever the rates are.

### Override 5: rounded figures in the summary, with the exact amount one step away

- **What the AI did.** The generated summary panel showed only rounded figures (EUR 6.96m, 1.38m, 415.6k). There was no way to see the exact amounts that the answers quote, and the credit-note line was the only figure shown in full, so the panel mixed two styles.
- **Why I changed it.** The point of the app is that numbers can be checked. If the overview says EUR 6.96m and an answer says EUR 6,964,721.16, an analyst should be able to confirm they're the same figure without leaving the screen. I still wanted the panel easy to scan, so I chose "rounded to read, exact one step away" over showing every amount to the cent.
- **What I caught in testing.** The AI's first version used the browser's built-in tooltip. When I tried it, the cursor changed but the amount never appeared: built-in tooltips wait about a second, need a perfectly still mouse, and don't exist on phones. I had it replaced with the app's own tooltip.
- **What it does now.** The headline keeps EUR 6.96m large, with EUR 6,964,721.16 underneath. Every rounded amount in the tables shows its exact value, in its own currency (for example "GBP 1,182,251.02" in the Original column), as soon as you hover over it, tab to it or tap it on a phone. Screen readers read out the exact value. A footer line explains the rule. The backend didn't change: `/summary` already returned every amount to the cent, so this is display only.
- **Files.** `frontend/src/components/SummaryPanel.tsx` (the `Amount` component), `frontend/src/styles.css` (`.amount`, `.amount-tip`).
- **How it was checked.** In a real browser: hover, keyboard focus and a phone tap all show the exact amount, and the tooltip stays inside the panel, including on the top row. There's no automated frontend test for it; the backend tests don't cover the UI.