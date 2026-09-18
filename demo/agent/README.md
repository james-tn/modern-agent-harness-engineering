# Equity Event Impact Analyst: runtime

The [demo guide](../README.md) explains the workflow, controls and evidence.
This document covers installation, CLI usage and runtime implementation.
The domain is a synthetic illustration, not investment advice.

## Install

Use Python **3.11 or later**. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r demo\agent\requirements.txt
.\.venv\Scripts\python.exe -m pytest demo\agent\tests -q
```

For live runs, configure access in the same terminal **before** starting the
server. Skip this block for the explicit offline profile:

```powershell
az login
$env:AZURE_OPENAI_ENDPOINT = "https://YOUR-RESOURCE.openai.azure.com/"
```

Start the console from the repository root:

```powershell
cd demo\agent
..\..\.venv\Scripts\python.exe -m equity_event serve
```

Open `http://127.0.0.1:8765`. The default is **Progressive / governed**, using
the `gpt-5.6-terra` deployment name on your own Azure resource. Replace the
example endpoint above with an HTTPS endpoint you can access; this repository
does not provide a shared backend or provision deployments. Authentication uses
`AzureCliCredential`; no API keys or telemetry service.
Switch deployment to `gpt-5.4` explicitly if needed. Failure never silently
changes model or switches to scripted output.

`AZURE_OPENAI_ENDPOINT` is required only for live runs. The **Scripted / offline**
profile and `run --model scripted` need neither Azure login nor an endpoint.

Dependencies are pinned to core **1.18.0**, OpenAI provider **1.14.3**,
Azure Identity **1.25.3** and OpenTelemetry SDK **1.44.0**. Provider versions
ship independently. The umbrella package is unnecessary. If a mirror lags, use
the [official release artifacts](https://github.com/microsoft/agent-framework/releases/tag/python-1.18.0)
or an approved index; do not silently downgrade.

## CLI usage

From `demo\agent`, the console and CLI use **the same `run_live_episode`**:

```powershell
# Live default; prompts for review on an interactive terminal.
..\..\.venv\Scripts\python.exe -m equity_event run

# Explicit offline safety net; real tools and seeded model calls, no Azure.
..\..\.venv\Scripts\python.exe -m equity_event run --model scripted

# Automated local verification, NEVER represented as a human approval.
..\..\.venv\Scripts\python.exe -m equity_event run --rehearsal-approval

# A second process with the same scope reads the first run's observation.
..\..\.venv\Scripts\python.exe -m equity_event run --memory-scope techhub-analyst
```

New runs use unique directories under ignored `out\live`; shared memory is
`out\live\memory`. `--output` goes before the subcommand. `run --config file.json`
accepts a complete or partial validated `HarnessConfig`; unknown fields fail.
The UI edits the same schema. Never overwrite evidence to "rerun" it.

The CLI exposes only `run` and `serve`. Retired A/B commands and generated
examples are superseded by this shared runtime and the
[curated evidence](../live-evidence/README.md). For offline execution, use
`run --model scripted`, not the old status-page workflow.

## Components and ownership

| Module | Responsibility |
|---|---|
| `live_config.py` | Validated concept settings and three switchable profiles |
| `live_model.py` | Token-only Azure Responses client and total model-request budget |
| `live.py` | Shared two-turn runtime, real callable tools, progressive exposure, gates and memory policy |
| `live_telemetry.py`, `live_trace.py` | Local native MAF span collection plus labeled application events |
| `ui.py`, `ui_assets/index.html` | Loopback console, run worker, operator approval and span-tree visualization |
| `live_analysis.py` | Strict arithmetic AST validation and reviewed Python/HTML/SVG rendering boundary |
| `domain.py`, `sources.py` | Synthetic source snapshots, real mock-API retrieval and provenance |
| `harness/policy.py`, `harness/verifier.py` | Mandatory information flow and independent executable checks |
| `harness/state.py`, `harness/ledger.py`, `harness/certificate.py` | Durable state, evidence and exact artifact hashes |
| `model.py`, `runs.py`, `analysis.py`, `progress.py` | Shared scripted-client, execution and approval helpers; historical fixture regression coverage |
| `skills/*/SKILL.md`, `tests/` | Predefined domain instructions and offline/live-opt-in regression coverage |

## What actually happens

**Progressive tooling.** MAF advertises names/purposes. The model invokes the
real `SkillsProvider.load_skill`, receiving full `SKILL.md` instructions. Loading
`financial-source-retrieval` exposes actual retrieval tools; loading
`abnormal-return-model` exposes `execute_analysis` on the next model call.
`FunctionInvocationContext.add_tools` and the filesystem store backing memory
are **experimental in 1.18**. Policy is always enforced, regardless of skill
selection. The all-loaded profile injects
the full configured skill set and exposes configured tools before the first call.

**Context and memory.** Planning and execution reuse one `AgentSession`; its
serialized state is written to `agent-session.json`. A MAF `FileMemoryProvider`
has an explicit cross-episode scope and filesystem store. The factory's default
session-scoped memory is disabled only to replace it with this scoped provider.
The model lists/reads memory at the start and cites its source trace in the plan.
After checks and approval it writes a validated prior-run observation. A second
run can recall that record. Memory cannot grant permission, override current
policy, write arbitrary files or promote lessons. Compaction is **off**;
sanitized evidence and durable state are real, automatic context trimming is not.

**Execution and acceptance.** The model selects a date and authors a small
arithmetic expression. An AST allowlist admits only bounded arithmetic over
security/benchmark returns; reviewed code handles filesystem I/O and rendering.
Wrong-but-valid math or dates reach the verifier unchanged. Python `-I`, curated
environment and timeout are **not an OS sandbox**. Do not route arbitrary
generated Python through the legacy unrestricted runner.

Strict mode enforces all checks, asks for bounded correction, then stops/escalates
when attempts are exhausted. Observe-only may finish an **unverified preview**,
but cannot issue a verified certificate or write verified memory for it.
Passing checks never grants approval: the UI operator must approve the exact
artifact. `--rehearsal-approval` records an explicitly automated receipt.
Nothing sends email or publishes externally.

**Real versus simulated.** Live means the Azure model chooses function calls.
Source data remain synthetic snapshots/mock APIs. The offline tool client extends
the original scripted client and emits seeded function-call messages into the
same MAF invocation loop. Execution, checks, memory and OTel are still real,
but its reasoning and first wrong date are scripted. A live first-pass failure
is not guaranteed.

## Observability and evidence

The console uses **MAF's native OpenTelemetry agent, chat and tool spans**:
real trace/span IDs, parentage, durations, errors, arguments/results and token
usage where emitted. The local processor also captures in-flight spans.
Application events add skill selection/load/use, memory/recall, policy,
acceptance/correction and approval to the **same trace**. They are labeled
application signals, not claimed as native MAF domain checks.

`telemetry.json` is the local span-tree snapshot; `runtime-state.json` shares
its genuine OTel trace ID. `harness-config.json`, `agent-session.json`,
`verification-*.json`, per-attempt artifacts and `result.json` persist with it.
Successful approved runs also contain `evidence-certificate.json` and canonical
`dashboard.html`. Sensitive telemetry content is enabled only for this synthetic,
filtered fixture, with no HTTP headers, credentials or remote telemetry exporter.
Snapshot replacement retries transient Windows sharing violations. Exhausted
telemetry writes are logged and recorded in `export_health` and
`telemetry-health.json`; native spans remain available for recovery. A telemetry
export failure does not retroactively turn an admitted application result into
a failed episode. Inspect export health before using a saved trace as evidence.

## Testing and remaining boundaries

Normal pytest runs are offline-safe and exercise the same tools, progressive
loading, file memory, gates, budgets and server via the scripted function client.
On Windows, an additional test holds a real exclusive filesystem lock during an
episode and requires reported write failures, recovered telemetry and preserved
completion. It skips only on platforms without Windows sharing semantics.
The real model path also has opt-in coverage:

```powershell
$env:EQUITY_LIVE_TEST = "1"
..\..\.venv\Scripts\python.exe -m pytest tests\test_live_runtime.py -k real_azure -q
Remove-Item Env:\EQUITY_LIVE_TEST
```

Do not enable this in credential-free CI. Retained live evidence is separate
from tests and the original recording. A saved trace is replayed evidence, not a
new live run. This is a single-operator local demonstration, not a production
multi-tenant service, identity-verified approval system, general workflow
recovery engine or security sandbox. Budgets stop work; they do not prove success.
