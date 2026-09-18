# Retained harness evidence

These are actual console runs captured on September 17, 2026, not fabricated
traces or a video simulation. All source and portfolio data are synthetic.
The domain fixture is an available illustration. Nothing here is investment advice.

## Five-run comparison

| Role | Run directory | Actual outcome |
|---|---|---|
| Live warmup | [r-98af89a2478e80c2](r-98af89a2478e80c2/result.json) | Progressive, strict, approved; writes the first observation |
| Live recall | [r-179fbefb3be66bde](r-179fbefb3be66bde/result.json) | New process, same memory scope; reads and cites the warmup trace |
| Live all-loaded | [r-34c80beda5b222d1](r-34c80beda5b222d1/result.json) | Full skill bodies/tools up front, memory off, observe-only; genuinely passes |
| Seeded offline, observe | [r-5a5e7d319bfbd70e](r-5a5e7d319bfbd70e/result.json) | Wrong date reaches the verifier; uncertified preview, no approval or memory write |
| Seeded offline, strict | [r-4a832f54f04fe8ae](r-4a832f54f04fe8ae/result.json) | Same seeded wrong date; failed check, bounded correction, passing second attempt |

The first three used the recording environment's Azure `gpt-5.6-terra`
deployment; those captures do not grant access to that backend. All three passed on
the first analysis attempt. Do not present the deliberately seeded offline error
as a spontaneous live-model failure, or claim that all-loaded necessarily makes
more calls or consumes more total tokens.

All retained approval receipts say `automated-ui-validation-not-human`.
The browser test deliberately exercised the real blocking approval interface;
these receipts are **not human review**. A presenter must inspect and approve a
new result themselves. Certification here means the local artifact passed the
checks and the recorded approval boundary, not external publication.

## Exact landmarks for slides 9-11

Within each directory, `harness-config.json` is the effective configuration;
`telemetry.json` contains native MAF spans and separately labeled application
events; `runtime-state.json` contains durable domain state. The two conversational
phases reuse the session serialized in `agent-session.json`.

| Show | Concrete evidence |
|---|---|
| A real model-issued call | Warmup trace `4033a15ace7384723a22f98eda1b44de`, native span `1cb2b5c72a809831`, `execute_tool load_skill`, call ID `call_OiS60meyHl6TBi2EiHAP9PMd`; arguments select `financial-source-retrieval`, result contains the full skill |
| Mid-run selection and loading | Same warmup trace: `skill_selected` event `:000026`, then `skill_loaded` `:000027` for `abnormal-return-model`; this enables the executable analysis tool, not an inert metadata list |
| Memory actually crossing runs | Recall trace `2bb54fd966cbb5f1f14bb3519be03d67`, event `:000008`, `cross_run_memory_recalled`; `source_trace_id` is the warmup trace and the recalled rule is `after_close -> next trading day` |
| Failed acceptance without false certification | Offline observe trace `bcebee7178409c2aa2ad94ff6a84a2ad`, `acceptance_evaluated` `:000036`, followed by `unverified_preview` `:000037`; `event_date_alignment` is false |
| Concrete bounded correction | Offline strict trace `197a9023d739f58e59d7d4291823e311`: failed acceptance `:000036`, `bounded_correction_requested` `:000037`, passing acceptance `:000043` |
| Evidence-bound completion | A successful directory's `evidence-certificate.json` includes source/output hashes, checks and approval kind; the observe-only failed directory has no certificate |

Event IDs are the full trace ID followed by the suffix shown, for example
`2bb54fd966cbb5f1f14bb3519be03d67:000008`. Native call IDs come from MAF, not from
these application annotations. `skill_used` only means the gated tool executed
with the relevant instruction loaded; it is not a claim about hidden reasoning.

The warmup also preserves a transient Windows state-snapshot error at
`:000029`. The model continued and completed. It is not erased or relabeled as
a policy violation. Subsequent testing found a separate telemetry-file rename
race; persistence recovery is covered by regression tests rather than by
rewriting these historical traces.

The decisive Windows regression is
[`test_windows_telemetry.py`](../agent/tests/test_windows_telemetry.py): a real
`CreateFileW` deny-all handle locks `telemetry.json` during the actual scripted
episode. It requires genuine WinError 5 export failures, recovered native
evidence, and an unchanged completed/certified result. Mocked exhaustion tests
also cover nonfatal persistence failure. The
[five-run polling report](polling-regression.json) is supplemental smoke evidence:
it observed no exhausted writes and does not alone prove lock recovery.

For stage budgeting, the retained live warmup, recall and all-loaded examples
reached `approval_requested` in **101.4, 58.4 and 66.6 seconds**, respectively.
These are individual trace measurements, not latency guarantees or comparative
benchmarks; subsequent review waits are excluded. The initial input-token counts
were 3,646, 3,703 and 3,461, respectively. Progressive loading is demonstrable
here, but these examples do **not** establish a token-saving advantage.

## Rehearsal and replay

For **new** runs, use the ignored default output:

```powershell
cd demo\agent
..\..\.venv\Scripts\python.exe -m equity_event serve
```

To inspect these saved runs through the console instead, stop that server and
use the retained output directory:

```powershell
..\..\.venv\Scripts\python.exe -m equity_event --output ..\live-evidence serve
```

Open `http://127.0.0.1:8765`, then **Observe** and choose the run. Call it
**saved live evidence**, not a newly completed episode. Use the default ignored
output for subsequent rehearsals so this evidence set is not mixed with new
runs. Never overwrite a retained run directory.

Warm one live run before the talk. During the five-minute slot, start one
governed run, inspect its actual load and recall, then review the saved seeded
near-miss/correction. Switch to saved evidence if endpoint latency consumes the
slot. The old embedded 164-second video predates this implementation and proves
none of its live-loading or cross-run-memory behavior.

`manifest.json` names the five authoritative examples. The deck validator checks
native model/tool-call correlation, skill lifecycle, memory provenance,
acceptance and certificate hashes. Mutation tests must reject unsupported
loading, fabricated recall and uncertified output presented as success.
Git attributes preserve recorded evidence bytes and the Windows checkout
endings of existing certificate inputs/legacy artifacts. Do not reformat
certificate-bearing files without regenerating and reviewing their evidence.

Screenshots of the saved live recall run: [console and profiles](screenshots/define.png),
[native skill call](screenshots/native-skill-call.png), and
[cross-run memory](screenshots/cross-run-memory.png). The console labels saved
runs explicitly; the idle action is **Run harness**, and successful review uses
**Approve local result**.
