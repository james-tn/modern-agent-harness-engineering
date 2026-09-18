# Modern Concepts and Techniques in Agent Harness Engineering

**Presenters:** James Nguyen, Alexandre Delarue and Kunwarpreet Behar

**Subtitle:** From context-aware agents to adaptive, governed runtimes

**Audience:** senior engineers, architects and AI practitioners who already know
agent basics, RAG, MCP and tool calling.

**Start here:** [PowerPoint](Modern-Agent-Harness-Engineering.pptx) ·
[presenter runbook](demo/README.md) · [runtime setup](demo/agent/README.md).

## Public snapshot and delivery plan

This public educational snapshot contains the editable presentation, executable
demo and retained synthetic evidence. It excludes private planning material and
earlier development history.

The proposed allocation is **30+15: 30 minutes prepared, including a five-minute
harness walkthrough, plus 15 minutes of discussion**. The 13-slide storyline is
history → harness components and autonomy → three practices → walkthrough →
discussion. The practices are **progressive tooling**, **intelligent context /
context hygiene**, and **acceptance gates**.

James owns history and the walkthrough, Alexandre components/autonomy and
acceptance gates, and Kunwarpreet tooling and context. All three facilitate
discussion. Exact timings and the synthetic equity fixture are presentation
choices, not universal requirements. This is not a fixed 45-minute lecture;
adjust discussion to the usable session time.

## Story and learning outcomes

Prompt engineering, context engineering and harness engineering expand the
engineering boundary; they do not replace one another. Context engineering can
already be dynamic. The harness connects instructions, context, tools/skills,
execution, memory/state, control gates and telemetry to enable **bounded autonomy**.

Participants should leave able to expose capabilities progressively without
deferring policy, preserve goals and relevant evidence through context changes,
and use real acceptance checks with bounded feedback and separate human approval.
Conceptual slides are framework-neutral. Microsoft Agent Framework **1.18.0**
appears only as the walkthrough implementation vehicle.

## Speaker ownership — proposed exact allocation

| Time | Section | Owner |
|---|---|---|
| 0:00–6:00 | Welcome and prompt → context → harness history | James Nguyen |
| 6:00–14:00 | Harness components and bounded autonomy | Alexandre Delarue |
| 14:00–22:00 | Progressive tooling and intelligent context / context hygiene | Kunwarpreet Behar |
| 22:00–25:00 | Acceptance gates | Alexandre Delarue |
| 25:00–30:00 | Define → run → observe walkthrough | James Nguyen |
| 30:00–45:00 | Discussion — proposed slot, adjusted to usable time | James Nguyen, Alexandre Delarue and Kunwarpreet Behar |

Prepared ownership totals: James 11 minutes, Alexandre 11 minutes, Kunwarpreet
8 minutes. Full speaker names are visible on the cover, agenda and each slide;
notes name the next speaker and topic at each handoff.

## Slide-to-agenda mapping

**11 prepared slides, one discussion slide, one untimed references slide.**
The five-minute demo occupies slides 9–11. Prepared content ends at **30:00**;
slide 12 reserves discussion, not another lecture section.

| Slide | Title | Presenter | Cumulative timing | Segment |
|---:|---|---|---|---|
| 1 | Modern Concepts and Techniques in Agent Harness Engineering | James Nguyen | 0:00-0:30 | Prepared |
| 2 | A short talk. A harness walkthrough. A discussion. | James Nguyen | 0:30-1:00 | Prepared |
| 3 | From shaping a call to engineering an episode | James Nguyen | 1:00-6:00 | Prepared |
| 4 | What’s inside a harness? | Alexandre Delarue | 6:00-10:00 | Prepared |
| 5 | Autonomy is a controlled loop—not an unlimited one | Alexandre Delarue | 10:00-14:00 | Prepared |
| 6 | Progressive tooling: discover, then load | Kunwarpreet Behar | 14:00-18:00 | Prepared |
| 7 | Intelligent context: preserve signal, remove clutter | Kunwarpreet Behar | 18:00-22:00 | Prepared |
| 8 | Acceptance gates: test the work, not the confidence | Alexandre Delarue | 22:00-25:00 | Prepared |
| 9 | Demo: define the harness | James Nguyen | 25:00-26:00 | Demo |
| 10 | Demo: run and observe | James Nguyen | 26:00-29:00 | Demo |
| 11 | Demo: prove loading, recall and acceptance | James Nguyen | 29:00-30:00 | Demo |
| 12 | Where do your agents struggle? | James Nguyen, Alexandre Delarue and Kunwarpreet Behar | 30:00-45:00 | Discussion — proposed |
| 13 | Primary sources and demonstration boundaries | James Nguyen, Alexandre Delarue and Kunwarpreet Behar | 45:00 | Untimed references |

## Walkthrough boundary

The equity fixture is an **available synthetic illustration**. Its financial
story and methodology are not the presentation's focus. All company,
market and portfolio data is synthetic and illustrative, not investment advice.
The default console profile uses a **gpt-5.6-terra** deployment through
Azure CLI token authentication. Configure your own `AZURE_OPENAI_ENDPOINT` and
model access as described in the runtime guide; no hosted backend is provided.
No API keys are needed. The **Define → run →
observe** console edits the same runtime used by the CLI: progressive versus
all-loaded skills, available tools, memory scope, budgets and acceptance strictness.

The live model issues real MAF function calls. `SkillsProvider.load_skill` returns
full instructions on demand; loading the relevant skill exposes executable domain
tools on subsequent model calls. A single `AgentSession` preserves both planning
and execution turns. A scoped MAF `FileMemoryProvider` persists a validated
observation which a later episode can read and cite. Mandatory policy never waits
for skill selection. MAF OpenTelemetry supplies the agent/chat/tool span tree;
application skill, memory and gate events join that same trace.

Model-authored code is deliberately **constrained arithmetic in a reviewed
Python/HTML/SVG template**, not arbitrary host code. `python -I` is not an OS
sandbox. Market sources remain synthetic snapshots and mock APIs; compaction is
off. Memory is a verified observation, not automatic policy or lesson promotion.

The **Scripted / offline** profile exercises the same callable tools, memory and
verifier without network access. Its first wrong event date is explicitly seeded:
observe-only exposes an uncertified near-miss; strict mode requests correction.
Live errors, ordering, counts, wording and latency are not deterministic, and a
live run may pass on its first attempt. Never claim a scripted failure was live.

The original August 24, ~164-second narrated video is embedded on **slide 10** as
a **legacy scripted fallback**, not evidence of the new UI, live model calls,
on-demand loading or cross-run memory. It is not a recording of the 1.18 upgrade,
the planning meeting or a live human approval. Do not combine its full playback
with the live console walkthrough inside the same five-minute slot.

## Repository map

| Location | Purpose |
|---|---|
| [`deck/`](deck/README.md) | Editable generator, citations and schedule/speaker/media validation |
| [`demo/`](demo/README.md) | Presenter ownership map and five-minute walkthrough instructions |
| [`demo/agent/`](demo/agent/README.md) | Live/configurable runtime, local console, native MAF telemetry and offline tests |
| [`demo/live-evidence/`](demo/live-evidence/) | Retained live and explicitly scripted console-run evidence |
| [`demo/sample-input/`](demo/sample-input/) | Synthetic source data and policy fixtures |
| [`demo/media/`](demo/media/) / [`recording/`](demo/recording/README.md) | Preserved legacy video, cover, provenance metadata and storyboard |

## Generate and validate

Deck generation requires Node.js and npm. The full validator also requires
Windows PowerShell and `ffprobe` from FFmpeg. Commands below use PowerShell.

```powershell
npm ci
npm run check
```

The canonical deck is written to the repository root. Runtime setup is separate;
do not reinstall or regenerate the unchanged fixture merely to rebuild slides.

## Source map

Public URLs and precise supported claims are also in the speaker notes.

| ID | Source and scope |
|---|---|
| L | This README and runbook — proposed timing, speaker ownership, slide count and available fixture |
| V1 | [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — dynamic curation and hygiene |
| V2 | [Tool Search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) — discovery/deferred loading, no performance statistics used |
| V3 | [Managed agents](https://www.anthropic.com/engineering/managed-agents) — session/context/execution separation |
| V4 | [Long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — progress and end-to-end checks |
| M1 | [Agent Harness](https://learn.microsoft.com/en-us/agent-framework/concepts/harness) — framework composition |
| M4 | [Python 1.18 changelog](https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/CHANGELOG.md) and [function-tool limits](https://learn.microsoft.com/en-us/agent-framework/agents/tools/function-tools#limit-automatic-tool-invocation) — pinned runtime and best-effort inner-loop budgets |
| D1 / D2 / D3 | Configurable runtime / actual skill and tool calls / native trace, memory and acceptance evidence |
| M5 | [Recording metadata](demo/media/equity-event-harness-demo.metadata.json) — original Foundry narration and exact media hashes |

The legacy video's exact hashes and narration provenance remain in its metadata;
the current implementation and retained evidence are repository-local.
Advanced evolution, proof-carrying research, memory virtualization and detailed
financial A/B analysis are not part of the prepared narrative.
