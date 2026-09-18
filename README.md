# Modern Concepts and Techniques in Agent Harness Engineering

From context-aware agents to adaptive, governed runtimes.

A practical guide for engineers who already know agents, RAG, MCP and tool
calling. The focus is the runtime around the model: how to make a complete
episode controlled, inspectable and repeatable.

[Slides](Modern-Agent-Harness-Engineering.pptx) ·
[Demo guide](demo/README.md) · [Runtime setup](demo/agent/README.md) ·
[Captured evidence](demo/live-evidence/README.md)

## From prompts to complete episodes

The unit of engineering is expanding from the model's next response to the
complete agent episode. These disciplines build on one another:

| Scope | Main question | Engineering responsibility |
|---|---|---|
| Prompt engineering | What should this call do? | Instructions, examples and output expectations |
| Context engineering | What does this step need? | Relevant instructions, tools, evidence and history |
| Harness engineering | What may happen next, and when is the work done? | Execution, state, policy, verification, budgets and recovery |

Context engineering can already be dynamic. Harness engineering does not replace
it; it adds controls that need not appear as tokens. A model can propose a good
answer without proving that an artifact exists, a calculation is correct, or an
action is authorized.

## What a harness controls

A harness connects the model to its operating environment:

- **Instructions and context:** the goal, constraints and evidence for the next step.
- **Tools and skills:** available capabilities and the instructions for using them.
- **Execution:** where actions run, what they can access, and their time limits.
- **Memory and state:** durable progress, observations, evidence and decisions.
- **Control and acceptance:** permission checks, verification, approval and stop conditions.
- **Telemetry:** a trace of actual model requests, tool calls and control decisions.

Autonomy is a bounded feedback loop, not permission to continue indefinitely:

```text
Goal + constraints -> select context/capabilities -> act -> observe -> evaluate
                                                         |
                            continue / correct / stop / escalate / complete
```

Budgets limit cost and duration. No-progress guards limit repeated ineffective
actions. Neither proves success: completion needs its own acceptance contract.

## Three engineering practices

### Progressive tooling

Expose capability names and purposes first, then load detailed instructions and
enable relevant tools when needed. This keeps the working set focused and makes
capability selection observable.

Selection is not permission. Mandatory policy, access checks and execution limits
must remain active even when a related explanatory skill has not been loaded.
Loading a skill also does not prove the model reasoned correctly; inspect its
actions and verify their results.

### Intelligent context and context hygiene

Preserve the goal, non-negotiable constraints, relevant evidence and unresolved
uncertainty. Retrieve what the next decision needs instead of repeatedly adding
every available document or tool result.

Separate temporary model context from durable state. Keep progress and evidence
references outside the context window; where compaction is implemented, retain
pointers to original material and validate what is written back. Memory is input
to reasoning, not an authority that can override current policy.

This addresses goal drift without assuming a longer context window is the only
solution. The included demo implements durable state and scoped memory;
automatic compaction is **off**.

### Acceptance gates

Define completion before execution. Check actual artifacts, calculations,
required content and policy constraints rather than accepting the model's
confidence or its declaration that it is done.

Return concrete failures to a bounded correction loop. If no permitted attempt
remains, stop or escalate. Passing checks and obtaining approval are separate:
correctness does not grant permission, and approval cannot make an incorrect
result correct.

The goal is consistent enforcement across runs, not identical model wording or
an identical sequence of tool calls.

## Demo: Equity Event Impact Analyst

The agent produces an earnings-event briefing for the fictional company **ACX**:
source-backed findings, benchmark-adjusted returns and charts. All company,
market and portfolio data is **synthetic and illustrative, not investment advice**.

The central failure example is deliberately simple: an earnings announcement
after market close must map to the next trading day. A report can contain correct
arithmetic for the wrong day, render successfully, and still be unacceptable.

The configurable console makes the harness controls visible:

| Control | Observable behavior |
|---|---|
| Progressive capabilities | Actual model-issued `load_skill` calls and newly exposed executable tools |
| Context and memory | One session across planning/execution; validated observations recalled across runs |
| Execution boundary | Constrained arithmetic inside reviewed Python/HTML/SVG rendering code |
| Strict acceptance | Independent checks, concrete failures and bounded correction |
| Approval and completion | Review of the exact verified artifact, followed by an evidence certificate |
| Observability | Native model/tool spans plus labeled application events in the same trace |

Microsoft Agent Framework **1.18.0** is the implementation vehicle, not the
definition of harness engineering. The application supplies the domain rules,
source adapters, execution constraints, verifier, console and completion policy.

## Run and explore

Follow [runtime setup](demo/agent/README.md#install), then start the console from
the repository root:

```powershell
cd demo\agent
..\..\.venv\Scripts\python.exe -m equity_event serve
```

Open **http://127.0.0.1:8765/**. Select **Scripted / offline** before running if
you have no Azure access. Its seeded model calls still exercise real tools,
execution, memory, verification and telemetry.

For the default live profile, configure your own `AZURE_OPENAI_ENDPOINT` and
deployment access before starting the server. Authentication uses Azure CLI
tokens; this repository provides neither API keys nor a shared hosted backend.

The [demo guide](demo/README.md) explains the controls, all acceptance checks,
memory lifecycle, comparison exercises and output files. The
[captured evidence](demo/live-evidence/README.md) distinguishes genuine live runs
from explicitly seeded offline examples.

## Boundaries

The model can be live while the source data remains synthetic. Retrieval tools
read local snapshots and mock APIs, not arbitrary web research or live prices.
The scripted wrong-date failure is intentional; a live model may pass on its
first attempt.

Python `-I` is **not an OS sandbox**. The supported execution path admits only
validated arithmetic in a reviewed template. Memory stores a predefined
validated observation, not autonomous policy changes or open-ended learning.
Some framework surfaces used for progressive exposure and filesystem memory are
experimental. This is a local demonstration, not a production multi-tenant system.

The [legacy recording](demo/recording/README.md) predates the current live console;
it is not evidence of live skill loading or cross-run memory.

## Further reading

- [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents): dynamic curation and context hygiene.
- [Tool Search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool): capability discovery and deferred loading.
- [Managed agents](https://www.anthropic.com/engineering/managed-agents): separation of session, context and execution.
- [Long-running harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): progress and end-to-end verification.
- [Agent Harness](https://learn.microsoft.com/en-us/agent-framework/concepts/harness) and [Python 1.18 changelog](https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/CHANGELOG.md): the framework composition used by this demo.

For editable slide generation and artifact validation, see [deck tooling](deck/README.md).
