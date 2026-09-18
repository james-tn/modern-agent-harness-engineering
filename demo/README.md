# Equity Event Impact Analyst demo

A convincing report is not the same as a correctly completed task. This demo
uses an earnings-event briefing to make that difference observable.

The fictional company **ACX** announces earnings after market close. The agent
must assemble evidence, calculate benchmark-adjusted returns, generate a charted
briefing and satisfy the harness's acceptance and approval requirements.
All company, market and portfolio data is **synthetic and illustrative, not
investment advice**.

[Runtime setup](agent/README.md#install) ·
[Captured runs](live-evidence/README.md) · [Source fixtures](sample-input/)

## What the agent does

The runtime requires a plan before domain execution and evidence before completion:

1. List and read scoped memory when enabled, then record a five-task plan.
2. Discover available skills and load needed instructions through actual tool calls.
3. Retrieve the public snapshot and internal policy, portfolio, thesis and lesson fixtures.
4. Execute a model-authored arithmetic expression in reviewed rendering code.
5. Independently verify the generated artifacts and correct failures within budget.
6. Request operator approval for the exact verified artifact.
7. Retain the validated observation when memory is enabled, then emit a completion certificate.

Planning and execution share one `AgentSession`. A new episode has a new session;
cross-run continuity comes from the separate file-memory store.

The live model's ordering, wording, counts and latency can vary. The harness
enforces the required boundaries rather than replaying a fixed live transcript.

## Configure and run

After [installing the runtime](agent/README.md#install), start the console from
the repository root:

```powershell
cd demo\agent
..\..\.venv\Scripts\python.exe -m equity_event serve
```

Open **http://127.0.0.1:8765/**. For live runs, set `AZURE_OPENAI_ENDPOINT` and
authenticate with `az login` in the server's terminal before starting it.
Otherwise select **Scripted / offline** before clicking **Run harness**.
The backend never silently switches from live to scripted.

| Profile | Model and capabilities | Memory and gates |
|---|---|---|
| **Progressive / governed** | Live Azure model; discover, load and use skills on demand | Shared memory enabled; strict acceptance |
| **All-loaded / observe-only** | Live Azure model; full configured skills/tools available up front | Cross-run memory off; failed output may remain an unverified preview |
| **Scripted / offline** | Seeded model-issued calls, but real tool execution and checks; no Azure required | Separate offline memory scope; strict acceptance by default |

Editable settings include skill/tool availability, memory enablement and scope,
execution attempts, model/tool-call ceilings, execution timeout and gate mode.
Changes apply to the **next run**, not an episode already in flight.

Mandatory policy, the arithmetic allowlist, local telemetry and separate approval
cannot be disabled. Automatic compaction is off. Python `-I` is not an OS sandbox.

## Progressive skill loading

In progressive mode the model initially receives skill names and purposes.
It calls `load_skill` for full instructions. Loading `financial-source-retrieval`
exposes retrieval tools; loading `abnormal-return-model` exposes the analysis tool.
Execution also requires the date-alignment and briefing skills.

In **Observe**, expand a native `execute_tool load_skill` span to inspect the
model's call ID, arguments and returned instructions. Application events distinguish
`skill_catalog_discovered`, `skill_selected`, `skill_loaded`, `tools_exposed` and
`skill_used`. Selection metadata alone is not proof of loading.

All-loaded mode supplies instructions and configured tools before the first call.
This is an exposure comparison, not a guarantee of lower token usage or better
accuracy in either mode.

## Strict acceptance gates

`verify_analysis` runs deterministic Python checks outside the model's reasoning:

| Check | What it establishes in this fixture |
|---|---|
| `script_execution` | Successful execution, required artifacts and valid machine-readable output |
| `independent_recalculation` | Stock, benchmark and adjusted returns agree with a separate recomputation |
| `approved_method` | The output specifies adjusted prices and the policy-approved benchmark |
| `claim_provenance` | Required source IDs are present |
| `required_sections` | All six required section keys are present |
| `restricted_data_excluded` | Known restricted portfolio fields and fixture values are absent |
| `causal_claim_guard` | The seeded untrusted causal claim and selected unsupported causal wording are excluded |
| `chart_data_integrity` | Embedded chart data matches the analysis series |
| `event_date_alignment` | The after-close announcement maps to the next supplied trading date |

The required sections are event summary, market reaction, portfolio exposure,
thesis update, risks/uncertainties, and sources/methods. These checks are specific:
source-ID presence is not sentence-level fact checking, and matching chart data
is not a complete visual-quality test.

A failed strict check returns concrete feedback and emits
`bounded_correction_requested`. The default permits **three executions total**;
model/tool budgets and a no-progress guard also bound the episode. Failed output
cannot obtain approval or certification.

After a pass, inspect the dashboard and choose **Approve local result** or decline.
The runtime checks artifact hashes around approval and completion. Permission is
separate from correctness, and an approval cannot authorize changed bytes.

Observe-only runs the same checks. A failed result may end as an
`unverified_preview`, but receives no approval, verified memory write or certificate.

### Compare a near-miss with bounded correction

Select **Scripted / offline**, change **Acceptance gates** to **Observe only**,
and run. The report renders, but its first analysis uses the announcement date:

```text
event_date_alignment: FAIL
After-close event must map to 2026-08-06; analysis used 2026-08-05.
```

The arithmetic is correct for the wrong day. Switch to **Strict** and start a new
run: the same seeded defect produces specific feedback, correction, another
verification and then a separate approval request. This is deliberate fault
injection, not a claim that a live model spontaneously made the mistake.

## Recall and retain observations

This setting controls **cross-run memory**, not the current episode's conversation
or durable plan. With memory off, PLAN and EXECUTE still share their session.

After passing checks and obtaining approval, the harness supplies an exact
`verified-run-observation` record. It contains a source trace ID, schema and policy
versions, the `after_close -> next trading day` rule, the approved benchmark and
synthetic-data classification. The model must use `file_memory_write` to persist
that record; arbitrary reflections, files and policy changes are rejected.

The default location is:

```text
demo\agent\out\live\memory\techhub-analyst\episode-memory.json
```

There is one latest-observation record per scope. Earlier episode evidence stays
in separate run directories. On the next run, the agent must list/read the record,
pass schema and current-policy validation, and cite the actual prior trace and
rule in its plan. Invented recall or a conflicting record is rejected.

To observe this, finish and approve one governed run, then run again with the
same memory directory and scope. Inspect:

```text
memory_index_read -> memory_read -> cross_run_memory_recalled
...
passing verification -> approval -> memory_written -> completion_admitted
```

Changing scope isolates recall. The offline preset uses `offline-rehearsal`.
The date rule was already engineered into policy: memory demonstrates continuity,
not autonomous discovery of a new rule or a measured accuracy improvement.
It never replaces the new run's acceptance checks. A trace ID is a provenance
link, not a cryptographic signature.

## Inspect a run

Native MAF spans show agent/model/tool activity, parentage, arguments/results,
errors, duration and token usage where emitted. Application events add domain
meaning in the **same trace**; the console labels their origin separately.

| Artifact | Purpose |
|---|---|
| `harness-config.json` | Effective settings for this episode |
| `agent-session.json` | The session reused across planning and execution |
| `runtime-state.json` | Plan, progress, decisions and domain events |
| `telemetry.json` | Native span tree and labeled application events |
| `verification-*.json` | Independent results for each checked attempt |
| `attempt-*/` | Executed code, analysis JSON and dashboard for each attempt |
| `evidence-certificate.json` | Source/output hashes, policy, checks and approval for an admitted result |

New output goes under ignored `demo\agent\out\live`. The
[evidence index](live-evidence/README.md) contains saved examples and exact trace
landmarks. Its approval receipts are explicitly automated validation, not human
review. Saved traces are evidence of earlier runs, not newly executed episodes.

## Implementation boundaries

MAF core **1.18.0** supplies sessions, skill/file-memory providers, function
invocation and native OpenTelemetry. Application code supplies synthetic adapters,
scope checks, execution constraints, policy, verification, approval and the console.
Progressive `add_tools` and the filesystem memory store are experimental.

Retrieval uses snapshots and mock APIs, not live market data or arbitrary web
search. Nothing sends email or publishes externally. There is no autonomous
harness repair, policy promotion, automatic compaction or unrestricted generated
Python execution.

The preserved [legacy recording](recording/README.md) uses a scripted model and
predates the current console. It does not demonstrate live model calls, on-demand
loading or cross-run memory.
