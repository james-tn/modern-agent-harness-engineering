# Agent harness presentation: presenter runbook

## Public snapshot and delivery plan

The proposed **30+15** allocation gives **30 minutes of prepared content,
including a five-minute walkthrough**, followed by 15 minutes of discussion.
Show configuration, tools, execution environment, memory/state, a run/trace and
skill loading/progressive disclosure.

The 13 slides, exact minute marks and synthetic equity fixture are presentation
choices. Adjust discussion to the usable session time; do not turn it into
another lecture segment. Private planning material is not part of this snapshot.

## Visible speaker ownership

| Proposed time | Responsibility | Speaker / handoff |
|---|---|---|
| 0:00–6:00 | Welcome and prompt → context → harness history | James Nguyen → Alexandre Delarue |
| 6:00–14:00 | Components and bounded autonomy | Alexandre Delarue → Kunwarpreet Behar |
| 14:00–22:00 | Progressive tooling and intelligent context / context hygiene | Kunwarpreet Behar → Alexandre Delarue |
| 22:00–25:00 | Acceptance gates | Alexandre Delarue → James Nguyen |
| 25:00–30:00 | Define → run → observe walkthrough | James Nguyen → all three presenters |
| 30:00–45:00 | Discussion, proposed slot | James Nguyen, Alexandre Delarue and Kunwarpreet Behar |

The cover and agenda show all three names; each content slide has its owner's
visible label. Notes name the next speaker/topic. James owns 11 prepared minutes,
Alexandre 11, Kunwarpreet 8. There are no extra divider slides or hidden lectures.

## James's five-minute walkthrough

Use slides 9–11 and the local console. Keep finance metrics out of the narration.
Start the server and complete one live governed run **before** the session so
the next run can genuinely recall its observation:

```powershell
cd demo\agent
..\..\.venv\Scripts\python.exe -m equity_event serve
```

Open `http://127.0.0.1:8765`. Installation, `AZURE_OPENAI_ENDPOINT` configuration
and `az login` are in the [runtime guide](agent/README.md#install). The default
live deployment name is `gpt-5.6-terra`, authenticated by `AzureCliCredential`.
Use your own Azure resource and deployment access, or the explicit offline profile.

| Slide / time | Show | Point to |
|---|---|---|
| 9 · 25:00–26:00 | **Define:** switch All-loaded / observe-only → Progressive / governed | Exposure, memory and acceptance visibly change; policy and human approval remain fixed. Click **Run harness** using the warmed memory scope. |
| 10 · 26:00–29:00 | **Run → Observe:** expand the native MAF execution tree | Actual model-issued `load_skill` and domain tools; memory read names the earlier trace. Review the dashboard after checks pass, then **Approve local result**. |
| 11 · 29:00–30:00 | **Prove:** compare with a prepared seeded offline trace | `event_date_alignment: false` in observe-only is an uncertified preview; strict mode records `bounded_correction_requested`. Explicitly call the defect seeded. Stop prepared content at 30:00. |

Do not budget for two serial live runs, two extra offline runs **and** video
playback inside five minutes. Warm the first live run and prepare the offline
contrast before the talk. During the talk, run one live episode and inspect the
saved near-miss/correction evidence. If latency consumes the slot, switch to the
retained live trace and call it **saved live evidence**, not a new completed run.

## Which profile proves what

| Profile | Teaching moment | Important boundary |
|---|---|---|
| **Progressive / governed** | Real Azure model, discover → load → use, shared memory, enforced checks | A live failure is not guaranteed; ordering, counts, wording, tokens and latency vary. |
| **All-loaded / observe-only** | Full skill bodies and domain tools up front; no cross-run memory | Checks still run. A failed result is visibly unverified and never certified. A live model may pass. |
| **Scripted / offline** | Seeded wrong announcement date, then real execution/check/correction | No live LLM. It uses the same callable tools, providers, verifier and native MAF telemetry. |

For the reliable premature-success comparison, choose **Scripted / offline**,
change **Acceptance gates** to **Observe only**, and run. The seeded wrong date
produces `unverified_preview`: it said done, but `event_date_alignment` is false.
Then choose **Strict** and rerun: the failed check requests bounded correction
before approval. This is a controlled fault demonstration, not evidence that
the live model spontaneously made that mistake.

The all-loaded/progressive contrast is genuine configuration and observable
context/tool exposure, not a promise that all-loaded always makes more calls or
uses more total tokens. Compare actual native spans, not invented counts.
Goal drift is a risk discussed in the talk; this fixture does not pretend to
measure spontaneous goal drift. The frozen plan and current-policy-over-memory
check show the control that prevents a stale observation from changing the task.

## Configuration is the talk made concrete

Every editable field is validated and affects the **next run**. Changes do not
mutate an episode already in flight.

| Concept | Editable parameters | Visible effect / fixed properties |
|---|---|---|
| Harness components | Profile and model deployment | Chooses the live or explicitly scripted client. The synthetic goal, mandatory instructions and local telemetry are fixed. |
| Bounded autonomy | Execution-attempt, model-request and tool-call ceilings; execution timeout | Changes stop/correction behavior. Identical-call no-progress threshold is fixed at three repeats; human review remains separate. |
| Progressive tooling | All-loaded/on-demand mode; available skills; enabled retrieval/execution tools | Preload versus actual `load_skill` events and changing callable surface. Removing a needed capability can block the task. Mandatory policy is not selectable. |
| Intelligent context / context hygiene | Memory on/off and scope | Read/write and cross-run recall events; changing scope isolates recall. One in-episode session preserves the plan. Compaction is off and read-only, not a simulated knob. |
| Acceptance gates | Strict versus observe-only | Failed check requests correction or produces an **unverified preview**. All executable checks still run; only verified, separately approved bytes can be certified. |

The Python boundary is a validated arithmetic expression inside reviewed
I/O/rendering code. The timeout changes execution; the AST allowlist does not
have an unsafe "off" option. Python `-I` is **not an OS sandbox**.

## What to point at in the trace

**MAF-native:** agent invocation, chat/model requests, `execute_tool` spans,
parent/child structure, actual OTel trace/span IDs, arguments/results, status,
duration and token usage where emitted. This is the source of the console's
execution tree, exported locally with no telemetry service.

**Application events in the same trace:** `skill_catalog_discovered`,
`skill_selected`, `skill_loaded`, `skill_used`, `tools_exposed`,
`memory_index_read`, `memory_read`, `cross_run_memory_recalled`, `memory_written`,
`acceptance_evaluated`, `bounded_correction_requested`, `approval_recorded`,
`completion_admitted`. These encode domain meaning that generic MAF spans do
not know; the console labels the distinction.

`skill_loaded` records a completed real `SkillsProvider.load_skill` call, not
preselection metadata. `skill_used` means a gated tool ran with that skill loaded,
not proof of the model's internal reasoning. Acceptance checks provide the
independent quality evidence.

`runtime-state.json` and `telemetry.json` share the genuine OTel trace ID.
`agent-session.json` persists the reused session; `episode-memory.json` in the
scoped MAF store contains the previous run's source trace. The memory record is
a validated observation subordinate to current policy, not automatically
promoted guidance. Detailed paths/IDs are in the retained
[live evidence index](live-evidence/README.md) and the per-run artifact view.

## Honest fallback boundaries

The source/data APIs remain synthetic snapshots and mocks. Core **1.18.0**
supplies the real session, skills, file-memory, tool invocation and OTel
components; application code supplies adapters, scope validation, execution,
policy, verifier, console and completion admission. Progressive `add_tools`
and the filesystem store backing memory are experimental. There is no arbitrary
internet research, autonomous harness repair, automatic compaction or
unrestricted generated-code execution.

For a network failure, explicitly select **Scripted / offline** and start a new
run. Its separate scope avoids confusing offline memories with live observations.
The UI and real tool execution remain available; the model source visibly changes.

Slide **10** also preserves the original
[164-second recording](media/equity-event-harness-demo.mp4). This is **legacy
scripted fallback**: no new UI, live model calls, model-driven mid-run loading
or cross-run memory. Its old “loaded” label means preselected paths. It uses
scripted reviewer approval, not a live human decision, and predates core 1.18.
Use it **instead of**, never in addition to, the complete console sequence.
[Storyboard, provenance metadata and media bytes](recording/README.md) remain unchanged.
A new recording would be useful; none was generated without a request.

## Discussion, not more lecture

At 30:00, all three invite a real case: tool overload, context/goal drift, or
premature success/repeated failure. Ask for the goal, the divergence, and observed
evidence. Kunwarpreet probes capability/context issues, Alexandre probes autonomy
and acceptance, and James connects the case to config/run/trace. End by identifying
one control to try and an observable success condition.
