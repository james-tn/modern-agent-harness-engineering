const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const OUT = process.env.DECK_OUT
  ? path.resolve(process.env.DECK_OUT)
  : path.join(root, "Modern-Agent-Harness-Engineering.pptx");
const video = path.join(root, "demo", "media", "equity-event-harness-demo.mp4");
const cover = path.join(root, "demo", "media", "equity-event-harness-demo-cover.png");
for (const file of [video, cover]) {
  if (!fs.existsSync(file)) throw new Error(`Missing recording asset: ${file}`);
}
const C = {
  bg: "07111F", panel: "0D1B2C", line: "294059",
  white: "F6FAFF", text: "D7E5F4", muted: "A0B4C9",
  blue: "2DA8FF", cyan: "27D3D1", violet: "AD91FF",
  green: "54D68C", amber: "F6B94A", coral: "FF7979",
};
const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "James Nguyen, Alexandre Delarue and Kunwarpreet Behar";
pptx.subject = "Modern Concepts and Techniques in Agent Harness Engineering";
pptx.title = pptx.subject;
pptx.company = "Microsoft";
pptx.lang = "en-US";
pptx.theme = { headFontFace: "Aptos Display", bodyFontFace: "Aptos", lang: "en-US" };
pptx.defineSlideMaster({
  title: "MASTER",
  background: { color: C.bg },
  objects: [
    { rect: { x: 0, y: 0, w: 13.333, h: 0.06, fill: { color: C.blue }, line: { color: C.blue } } },
    { line: { x: 0.75, y: 7.23, w: 11.83, h: 0, line: { color: C.line, width: 1 } } },
  ],
  slideNumber: { x: 12.18, y: 7.29, w: 0.4, h: 0.17, color: C.muted, fontSize: 9, margin: 0, align: "right" },
});

const JAMES = "James Nguyen";
const ALEXANDRE = "Alexandre Delarue";
const KUNWAR = "Kunwarpreet Behar";
const ALL = "James Nguyen, Alexandre Delarue and Kunwarpreet Behar";
const repo = "https://github.com/james-tn/modern-agent-harness-engineering";
const fixture = `${repo}/tree/main`;
const sources = {
  L: `Public presentation plan: 13 slides; 30 minutes prepared content, including a five-minute walkthrough, plus a proposed 15-minute discussion slot. Exact minute marks, speaker ownership and the synthetic equity fixture are presentation choices. Adjust discussion to the usable session time. README and presenter runbook: ${repo}`,
  V1: "Anthropic, Effective context engineering for AI agents, accessed 2026-08-17. Supports dynamic curation of instructions, tools, evidence and history. Context engineering is not inherently static; the prompt/context/harness progression describes expansion of responsibility. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents",
  V2: "Anthropic, Tool search tool, vendor documentation accessed 2026-08-17. Supports discovery and deferred loading of tool definitions. No token-reduction statistic or cross-runtime performance guarantee is used in this presentation. https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool",
  V3: "Anthropic, Managed agents, accessed 2026-08-17. Supports separating the durable session from temporary model context and execution resources. Architecture reference, not an isolation or universal durability guarantee. https://www.anthropic.com/engineering/managed-agents",
  V4: "Anthropic, Effective harnesses for long-running agents, accessed 2026-08-17. Supports progress artifacts, incremental work and end-to-end checks before claiming completion. Loop limits and no-progress escalation here are recommended application contracts, not claims about every framework. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents",
  M1: "Microsoft Learn, Agent Harness, updated 2026-08-25. Released create_harness_agent composition. https://learn.microsoft.com/en-us/agent-framework/concepts/harness\nPython 1.18.0 factory: https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/packages/core/agent_framework/_harness/_agent.py",
  M4: "Microsoft Agent Framework Python 1.18.0, released September 10. https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/CHANGELOG.md\nFunction-tool limits: https://learn.microsoft.com/en-us/agent-framework/agents/tools/function-tools#limit-automatic-tool-invocation\nThe inner-loop max_duration_seconds budget is best effort, counts approval waits and does not cancel a running tool or prove completion. FunctionInvocationContext.add_tools is experimental in 1.18; this demo uses it for progressive exposure.\nNative instrumentation: https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/packages/core/agent_framework/observability.py",
  D1: `Repository-local live implementation: live.py, live_config.py, live_model.py, live_analysis.py and ui.py. The default deployment name is gpt-5.6-terra, authenticated with AzureCliCredential; configure your own AZURE_OPENAI_ENDPOINT and deployment access. No API keys or shared hosted backend are provided. The model issues real executable function calls. Sources remain synthetic snapshots/mock APIs. Model-authored code is constrained arithmetic in a reviewed renderer, not arbitrary Python or investment advice. ${repo}/tree/main/demo/agent/equity_event`,
  D2: `MAF SkillsProvider advertises metadata and executes load_skill mid-run; application middleware exposes real domain tools after loading. A single AgentSession spans planning and execution, and a scoped MAF FileMemoryProvider persists a validated observation for later runs. FileSystemAgentFileStore is experimental in 1.18. Mandatory policy is always enforced; compaction remains off. ${repo}/tree/main/demo/agent/equity_event/live.py\n${repo}/tree/main/demo/agent/skills/event-date-alignment/SKILL.md\nMAF source: https://github.com/microsoft/agent-framework/blob/python-1.18.0/python/packages/core/agent_framework/_skills.py`,
  D3: `Repository-local retained console evidence: telemetry.json contains MAF-native agent/chat/tool spans with real OTel parentage and trace IDs. Application events in the same trace include skill_loaded, cross_run_memory_recalled, acceptance_evaluated and bounded_correction_requested. runtime-state.json uses the same trace ID. Live runs are nondeterministic; the offline profile's first wrong event date is seeded. ${repo}/tree/main/demo/live-evidence`,
  M5: `Original August 24 recording, 164.45 seconds, Microsoft Foundry gpt-4o-mini-tts / onyx. Prerecorded scripted model, synthetic data and explicit scripted reviewer approval. Metadata, request fingerprints and media hashes document provenance. The video is not a 1.18 run or evidence of model-driven skill loading. ${fixture}/demo/media\n${fixture}/demo/recording`,
};

function text(s, value, x, y, w, h, size = 20, color = C.text, options = {}) {
  s.addText(value, {
    x, y, w, h, fontFace: "Aptos", fontSize: size, color, margin: 0,
    valign: "mid", breakLine: false, isTextBox: true, ...options,
  });
}
function rect(s, x, y, w, h, color = C.line, fill = C.panel) {
  s.addShape(pptx.ShapeType.rect, {
    x, y, w, h, fill: { color: fill }, line: { color, width: 1.5 },
  });
}
function arrow(s, x, y, dx, dy, color = C.muted, end = true, dashed = false) {
  s.addShape(pptx.ShapeType.line, {
    x: dx < 0 ? x + dx : x, y: dy < 0 ? y + dy : y,
    w: Math.abs(dx), h: Math.abs(dy), flipH: dx < 0, flipV: dy < 0,
    line: { color, width: 1.7, endArrowType: end ? "triangle" : undefined, dash: dashed ? "dash" : undefined },
  });
}
function label(s, heading, detail, x, y, w, color = C.cyan) {
  text(s, heading, x, y, w, 0.48, 22, color, { bold: true });
  text(s, detail, x, y + 0.62, w, 0.86, 18, C.text, { valign: "top" });
}
let count = 0;
function slide({ title, subtitle = "", timing, speaker, segment = "prepared", explanation, talk, reference = "", handoff, refs, source, coverSlide = false }) {
  const s = pptx.addSlide("MASTER");
  count += 1;
  if (!coverSlide) {
    text(s, title, 0.75, 0.56, 11.83, 0.7, 32, C.white, { fontFace: "Aptos Display", bold: true });
    if (subtitle) text(s, subtitle, 0.75, 1.35, 11.83, 0.5, 18, C.muted);
  }
  text(s, `SOURCE: ${source}`, 0.75, 6.78, 11.83, 0.39, 10.5, C.muted);
  text(s, speaker, 0.75, 7.28, 8.25, 0.2, 10.5, C.muted);
  text(s, timing.includes("untimed") ? "UNTIMED REFERENCES" : timing, 9.2, 7.29, 2.55, 0.17, 9, C.muted, { align: "right" });
  const citations = refs.map((id) => {
    if (!sources[id]) throw new Error(`Unknown source ${id} on slide ${count}`);
    return `[${id}] ${sources[id]}`;
  }).join("\n\n");
  const backup = reference ? `\n\nPRESENTER REFERENCE (not additional prepared material)\n${reference}` : "";
  s.addNotes(`CUMULATIVE TIMING\n${timing}\n\nPRESENTER\n${speaker}\n\nSESSION SEGMENT\n${segment}\n\nSLIDE EXPLANATION\n${explanation}\n\nPRESENTER TALK TRACK\n${talk}\n\nHANDOFF\n${handoff}${backup}\n\nCITATIONS\n${citations}`);
  return s;
}

// 1. Three presenters; no fixed lecture-length claim.
{
  const s = slide({
    title: pptx.title, timing: "0:00-0:30", speaker: JAMES, coverSlide: true,
    explanation: "The session moves from the history of agent engineering to practical controls and a short harness walkthrough. All three presenters appear together.",
    talk: "James opens. Assume the audience knows agents, RAG, MCP and tool calling. We will explain what belongs around those calls, how it enables bounded autonomy, and three practices worth applying. Prepared material ends at minute 30 so the room has time to discuss real challenges. The exact 30+15 schedule is our proposed allocation; adapt discussion to the usable session time.",
    handoff: "James Nguyen continues with the agenda and visible speaker ownership.",
    refs: ["L"], source: "[L] Public presentation plan. Exact delivery timings are presentation choices.",
  });
  text(s, "Modern Concepts and Techniques\nin Agent Harness Engineering", 0.75, 1.0, 11.8, 1.8, 40, C.white, { bold: true, fontFace: "Aptos Display" });
  text(s, "From context-aware agents to adaptive, governed runtimes", 0.78, 3.02, 11.5, 0.55, 23, C.cyan);
  arrow(s, 0.9, 4.5, 11.4, 0, C.line, false);
  text(s, "HISTORY", 1.1, 4.78, 2.8, 0.48, 24, C.white, { bold: true });
  text(s, "AUTONOMY", 5.12, 4.78, 3.1, 0.48, 24, C.white, { bold: true });
  text(s, "PRACTICE", 9.53, 4.78, 2.8, 0.48, 24, C.white, { bold: true });
  text(s, "James Nguyen  ·  Alexandre Delarue  ·  Kunwarpreet Behar", 0.78, 6.0, 11.6, 0.52, 22, C.text);
}

// 2. A prepared-content cap, with discussion deliberately reserved.
{
  const s = slide({
    title: "A short talk. A harness walkthrough. A discussion.",
    subtitle: "Proposed delivery plan · clear topic ownership, with room for discussion",
    timing: "0:30-1:00", speaker: JAMES,
    explanation: "The agenda makes the storyline, content cap and speaker ownership explicit. Exact timings and the discussion allocation are delivery choices.",
    talk: "James: history first, Alexandre on components and bounded autonomy, Kunwarpreet on progressive tooling and intelligent context, Alexandre on acceptance gates, then James with a five-minute walkthrough. All three facilitate discussion. This deck proposes 30 minutes prepared, including five minutes of demo, plus a 15-minute discussion slot. It is not a fixed 45-minute lecture. Adjust discussion to the usable session time rather than adding lecture content.",
    handoff: "James Nguyen begins the prompt → context → harness history.",
    refs: ["L"], source: "[L] Proposed plan: 30 minutes prepared, including a five-minute demo, plus discussion.",
  });
  const stops = [
    ["0–6", "Welcome + history", JAMES],
    ["6–14", "Components + bounded autonomy", ALEXANDRE],
    ["14–22", "Progressive tooling + context hygiene", KUNWAR],
    ["22–25", "Acceptance gates", ALEXANDRE],
    ["25–30", "Harness walkthrough", JAMES],
    ["30–45", "Discussion", "James Nguyen · Alexandre Delarue\nKunwarpreet Behar"],
  ];
  text(s, "MINUTES", 0.85, 2.08, 1.6, 0.35, 17, C.muted, { bold: true });
  text(s, "SECTION", 2.65, 2.08, 5.8, 0.35, 17, C.muted, { bold: true });
  text(s, "SPEAKER", 8.8, 2.08, 3.7, 0.35, 17, C.muted, { bold: true });
  arrow(s, 0.85, 2.54, 11.65, 0, C.line, false);
  stops.forEach(([time, name, who], i) => {
    const y = 2.74 + i * 0.59;
    text(s, time, 0.85, y, 1.65, 0.44, 22, i === 5 ? C.amber : C.cyan, { bold: true });
    text(s, name, 2.65, y, 5.85, 0.47, 21, C.white);
    text(s, who, 8.8, y - (i === 5 ? 0.08 : 0), 3.75, i === 5 ? 0.72 : 0.44, i === 5 ? 14.5 : 20, C.text);
  });
  text(s, "Prepared content stops at 30:00. Discussion timing is proposed.", 0.85, 6.32, 11.6, 0.35, 20, C.amber);
}

// 3. History is expansion; context engineering is already dynamic.
{
  const s = slide({
    title: "From shaping a call to engineering an episode",
    subtitle: "Prompt → Context → Harness: expansion, not replacement.",
    timing: "1:00-6:00", speaker: JAMES,
    explanation: "Three engineering scopes build on one another. Dynamic context remains essential inside the larger runtime; the progression does not equate context engineering with static prompts.",
    talk: "1:00-2:15 — Prompt engineering shapes instructions for a model interaction. Good instructions still matter; this is not a story about abandoning one discipline for another.\n\n2:15-3:30 — Context engineering selects and structures instructions, tools, evidence and history for the next call. It can be dynamic: retrieval, summaries and changing tool availability are already part of it. Do not call context engineering static. A static everything-loaded prompt is one implementation choice, not the definition of context engineering.\n\n3:30-4:45 — Harness engineering takes responsibility for the episode around those calls: which action may execute, where it executes, what state persists, how observations update the next step, and when to continue, stop or escalate. Some controls never appear as tokens. A useful answer does not prove a file was produced, a side effect was safe, or a pending approval is still valid.\n\n4:45-6:00 — Use a neutral example: an assistant tasked with an approved report can make a plausible draft but still omit required evidence or stop before rendering the artifact. Better context helps it propose the right thing; the runtime owns the executable completion contract. Ask the audience to hold one such workflow in mind. The history slide is architectural synthesis, not an empirical claim that every organization crossed these stages on a date.",
    handoff: "James Nguyen → Alexandre Delarue: what components give that episode a dependable runtime?",
    refs: ["V1", "V4"], source: "[V1] Dynamic context curation. [V4] Long-running harness practices. Architectural synthesis.",
  });
  const stages = [
    ["PROMPT", "Shape instructions", "What should this call do?", C.violet],
    ["CONTEXT", "Assemble the working set", "What does this step need?", C.blue],
    ["HARNESS", "Control the episode", "What happens next—and when is it done?", C.cyan],
  ];
  stages.forEach(([name, unit, detail, color], i) => {
    const x = 0.85 + i * 4.13;
    text(s, name, x, 2.55, 3.55, 0.55, 28, color, { bold: true });
    text(s, unit, x, 3.42, 3.63, 0.85, 23, C.white);
    text(s, detail, x, 4.55, 3.6, 0.9, 19, C.muted);
    if (i < 2) arrow(s, x + 3.48, 2.85, 0.45, 0);
  });
  text(s, "Dynamic context remains a core part of the harness.", 0.85, 6.03, 11.6, 0.52, 26, C.white, { bold: true });
}

// 4. Components, not an additional taxonomy to memorize.
{
  const s = slide({
    title: "What’s inside a harness?",
    subtitle: "A practical map of responsibilities—not a universal component taxonomy.",
    timing: "6:00-10:00", speaker: ALEXANDRE,
    explanation: "Instructions/context, tools/skills, execution environment and memory/state surround control gates. Telemetry makes their decisions inspectable.",
    talk: "6:00-7:00 — Alexandre takes over. Start with instructions and context: the goal, constraints and evidence the model sees. Tools and skills define callable operations and reusable know-how. A skill is guidance and assets, not necessarily an executable function or a permission grant.\n\n7:00-8:00 — Execution environment determines where proposed actions actually run: process, container, sandbox, API identity and allowed filesystem/network scope. Do not infer isolation from the word harness. Memory/state records progress, evidence and decisions outside temporary model context; persistence semantics depend on the implementation.\n\n8:00-9:00 — Control and gates join the parts: validate inputs, choose the next operation, enforce permissions and budgets, inspect results, and ask for approval where needed. Telemetry records the decision path and failure point rather than only the final text.\n\n9:00-10:00 — Walk an action through the map: selected skill, proposed tool input, checked permission, execution, observed result, persisted state, next-step context. These boxes are an illustrative design decomposition, not a claimed standard or a count of mandatory framework classes. Ask which component currently owns each responsibility in the audience's system. Missing ownership matters more than missing a product feature.",
    handoff: "Alexandre Delarue continues: how those components enable bounded autonomy.",
    refs: ["V1", "V3", "V4"], source: "[V1] Context and tools; [V3] session/execution separation; [V4] progress and verification practices.",
  });
  label(s, "INSTRUCTIONS + CONTEXT", "Goal, constraints and relevant evidence", 0.95, 2.25, 4.35, C.blue);
  label(s, "TOOLS + SKILLS", "Operations and reusable know-how", 8.15, 2.25, 4.25, C.cyan);
  label(s, "MEMORY / STATE", "Progress, observations and decisions", 0.95, 4.7, 4.35, C.violet);
  label(s, "EXECUTION ENVIRONMENT", "Identity, permissions and isolation", 8.15, 4.7, 4.25, C.amber);
  rect(s, 5.13, 3.38, 3.05, 1.3, C.green);
  text(s, "CONTROL\n+ GATES", 5.38, 3.58, 2.55, 0.89, 24, C.green, { bold: true, align: "center" });
  arrow(s, 4.8, 3.4, 0.33, 0.35, C.line, false);
  arrow(s, 8.55, 3.4, -0.37, 0.35, C.line, false);
  arrow(s, 5.13, 4.28, -0.33, 0.22, C.line, false);
  arrow(s, 8.18, 4.28, 0.32, 0.22, C.line, false);
  text(s, "TELEMETRY  ·  Observe the path, not just the final response.", 0.95, 6.18, 11.45, 0.39, 21, C.muted);
}

// 5. Bounded autonomy is a runtime contract, not more retries.
{
  const s = slide({
    title: "Autonomy is a controlled loop—not an unlimited one",
    subtitle: "Preserve the goal, observe progress, and keep an explicit human boundary.",
    timing: "10:00-14:00", speaker: ALEXANDRE,
    explanation: "Goal → act → observe feeds an acceptance decision. Only useful, permitted progress continues; budgets, no-progress controls and escalation bound the loop.",
    talk: "10:00-11:00 — Autonomy means choosing subsequent actions without a person specifying every step. The harness makes that useful by preserving a goal and checking observations against it. Describe the loop as goal, act, observe, then an explicit decision—not an infinite stream of tool calls.\n\n11:00-12:00 — Continue only when there is useful progress, permission and budget. Preserve observations and completed work in durable state so repeated attempts do not forget their own failures. Budget total time, tool calls and spend as appropriate; use individual tool timeouts too.\n\n12:00-13:00 — A no-progress guard detects repeated equivalent actions or recurring failure codes with no new evidence. It should stop or escalate rather than merely rewrite the same prompt. Goal drift, doom loops and premature success are failure examples we will address through the three practices—not separate research sections.\n\n13:00-14:00 — Keep the human boundary explicit: unclear scope, insufficient authority, sensitive actions or exhausted budget require a person or a safe stop. Acceptance means meeting the task contract; approval means permission for the next action. Bounded autonomy is not the maximum number of steps allowed. It is a system that can explain why the next step is justified and when no further autonomous step is justified. These are recommended contracts; do not claim every framework provides them automatically.",
    handoff: "Alexandre Delarue → Kunwarpreet Behar: start with progressive tooling, then context hygiene.",
    refs: ["V3", "V4"], source: "[V3] Durable episode state; [V4] incremental progress and checks. Bounds are design recommendations.",
  });
  [["GOAL", 0.95, C.blue], ["ACT", 4.75, C.cyan], ["OBSERVE", 8.65, C.green]].forEach(([name, x, color]) => {
    rect(s, x, 2.37, 3.0, 0.94, color);
    text(s, name, x + 0.2, 2.63, 2.6, 0.4, 24, color, { bold: true, align: "center" });
  });
  arrow(s, 4.12, 2.83, 0.46, 0, C.cyan);
  arrow(s, 7.92, 2.83, 0.54, 0, C.green);
  arrow(s, 10.14, 3.45, 0, 0.64, C.green);
  text(s, "ACCEPT / CONTINUE\nSTOP / ESCALATE", 7.92, 4.32, 4.45, 0.92, 24, C.amber, { bold: true, align: "center" });
  arrow(s, 7.63, 4.81, -5.17, 0, C.line, false);
  arrow(s, 2.46, 4.81, 0, -1.32, C.line);
  text(s, "Durable state carries\nobservations forward", 0.97, 5.11, 5.72, 0.83, 21, C.violet);
  text(s, "Budget limit  ·  No-progress guard  ·  Human boundary", 0.95, 6.21, 11.43, 0.38, 23, C.white);
}

// 6. Practice one: progressive capability exposure.
{
  const s = slide({
    title: "Progressive tooling: discover, then load",
    subtitle: "Avoid exposing the entire capability catalog at every step.",
    timing: "14:00-18:00", speaker: KUNWAR,
    explanation: "Two lanes compare an all-loaded implementation with progressive disclosure. Mandatory policy is outside the optional capability selection.",
    talk: "14:00-15:00 — Kunwarpreet: the top lane is an all-loaded implementation—every tool definition and skill instruction enters the working set. That is not the definition of context engineering; it is one strategy that becomes harder to manage as the catalog grows.\n\n15:00-16:00 — In the progressive lane, discover names and descriptions, select candidates for the current intent, then load full definitions, instructions or resources when needed. Tools can be typed callable operations; skills can be local instructions plus assets. Keep their discovery metadata distinct from the act of invoking them.\n\n16:00-17:00 — Never defer mandatory policy, permissions or acceptance rules. A selector is not an authorization service. If confidence is low, expand the candidate set, clarify or stop rather than silently omit required capability. Tool Search documentation supplies a concrete deferred-loading pattern; there is no need for a statistics wall to teach it.\n\n17:00-18:00 — Design a trace that distinguishes discovered, selected, loaded and invoked. Those are different events, and a selected list is not evidence of loading: see the load call itself. In the later walkthrough James will show exactly that distinction in a live trace: skills discovered as metadata, then a model-issued load_skill call with its own span and call ID, then the tool invocation that follows. The legacy prerecorded fixture predates that and only shows preselection; do not read it as loading. Ask which capability in the audience's catalog is needed only at one stage.",
    handoff: "Kunwarpreet Behar continues with intelligent context and context hygiene.",
    refs: ["V1", "V2"], source: "[V1] Dynamic context curation; [V2] Tool Search deferred-loading pattern. No performance statistic claimed.",
  });
  text(s, "ALL-LOADED", 0.95, 2.35, 2.4, 0.42, 22, C.muted, { bold: true });
  text(s, "Entire catalog", 3.65, 2.35, 3.25, 0.46, 23, C.text);
  arrow(s, 7.25, 2.59, 0.86, 0, C.line);
  text(s, "Every step", 8.65, 2.35, 3.5, 0.46, 23, C.text);
  arrow(s, 0.95, 3.22, 11.35, 0, C.line, false);
  text(s, "PROGRESSIVE", 0.95, 3.73, 2.45, 0.43, 22, C.cyan, { bold: true });
  [
    ["DISCOVER", "Names / purpose", 3.75],
    ["SELECT", "Relevant candidates", 6.75],
    ["LOAD", "Needed detail", 9.75],
  ].forEach(([name, detail, x], i) => {
    text(s, name, x, 3.73, 2.5, 0.43, 23, C.cyan, { bold: true });
    text(s, detail, x, 4.45, 2.5, 0.83, 19, C.text);
    if (i < 2) arrow(s, x + 2.43, 3.97, 0.35, 0, C.cyan);
  });
  text(s, "Mandatory policy stays available. Selection never grants permission.", 0.95, 6.03, 11.42, 0.53, 23, C.amber);
}

// 7. Practice two: an anchored, curated working set.
{
  const s = slide({
    title: "Intelligent context: preserve signal, remove clutter",
    subtitle: "Protect the goal and constraints while the working set changes.",
    timing: "18:00-22:00", speaker: KUNWAR,
    explanation: "An anchored goal and relevant evidence form the temporary working context. Bulky results are trimmed; durable memory/state stays separately recoverable.",
    talk: "18:00-19:00 — Start with the goal and non-negotiable constraints. The latest tool output should not replace the task definition. Goal drift often looks like locally sensible work that no longer serves the original request.\n\n19:00-20:00 — Retrieve relevant evidence and bring forward the observations needed for the next decision. Trim repetitive logs, irrelevant source material and bulky tool results. Compact to a useful summary plus a pointer to the original, but do not drop unresolved uncertainty or the rule that the next action must satisfy.\n\n20:00-21:00 — Separate temporary context from durable memory/state. Keep progress, evidence references, decisions and approvals outside the working set, with explicit writeback and recovery behavior. A conversation transcript alone is not a reliable workflow state machine. The required fidelity depends on the task; this is practical context hygiene, not a memory-virtualization lecture.\n\n21:00-22:00 — Before the next step, ask whether the goal remains visible, the evidence is relevant, and the next action follows the current constraints. After compaction, check that the goal and acceptance rules still mean the same thing. Ask the audience what occupies their context but rarely changes the next decision. Removing those tokens must not remove evidence or safety obligations.",
    handoff: "Kunwarpreet Behar → Alexandre Delarue: acceptance gates decide whether the resulting work is actually done.",
    refs: ["V1", "V3", "V4"], source: "[V1] Context hygiene; [V3] session versus model context; [V4] explicit progress artifacts.",
  });
  label(s, "PRESERVE", "Goal + constraints\nUnresolved questions", 0.95, 2.4, 3.45, C.amber);
  label(s, "RETRIEVE / TRIM", "Relevant evidence\nCompact bulky results", 8.75, 2.4, 3.5, C.cyan);
  arrow(s, 4.25, 3.6, 0.75, 0, C.amber);
  arrow(s, 8.52, 3.6, -0.58, 0, C.cyan);
  rect(s, 5.2, 2.65, 2.56, 2.0, C.blue);
  text(s, "WORKING\nCONTEXT", 5.4, 3.12, 2.16, 0.93, 23, C.blue, { bold: true, align: "center" });
  arrow(s, 6.47, 4.8, 0, 0.41, C.violet, false);
  text(s, "DURABLE MEMORY / STATE", 2.64, 5.43, 7.65, 0.42, 24, C.violet, { bold: true, align: "center" });
  text(s, "Progress · evidence references · decisions · approvals", 1.74, 6.04, 9.44, 0.44, 21, C.text, { align: "center" });
}

// 8. Practice three: actual checks, not confident completion prose.
{
  const s = slide({
    title: "Acceptance gates: test the work, not the confidence",
    subtitle: "Correctness and approval answer different questions.",
    timing: "22:00-25:00", speaker: ALEXANDRE,
    explanation: "A proposal must pass real artifact/test checks before it can be approved. Specific failures return through a bounded correction loop; false success and doom loops have explicit exits.",
    talk: "22:00-23:00 — Alexandre: define acceptance before execution. Did the requested artifact exist? Did tests or independent calculations pass? Is required evidence present? Does the result obey constraints and render correctly? Successful execution is necessary for some tasks but not sufficient for correctness. A model saying complete is only a proposal.\n\n23:00-24:00 — Return specific failures, not a vague low score. Allow a bounded correction only when there is a plausible new action. Repeated failure with no new evidence should trigger the no-progress guard; a time/pass budget must also end the loop. This prevents both premature success and doom loops. Keep the failed check visible after correction rather than rewriting the trace into success.\n\n24:00-25:00 — Passing tests does not authorize a sensitive action. Approval is separate and should be bound to the actual output/action. Conversely, an approval cannot make incorrect work correct. If checks fail or the budget is exhausted, deny completion and preserve the evidence for review. Hand over to James to inspect actual code, state and the live console, with an explicitly labeled saved trace as fallback—not to compare financial returns.",
    handoff: "Alexandre Delarue → James Nguyen: five-minute harness walkthrough, configuration → run → trace/state.",
    refs: ["V4", "V1"], source: "[V4] End-to-end verification and progress; [V1] constraints and evidence. Approval boundary is a design contract.",
  });
  [["PROPOSE", 0.85, C.blue], ["CHECK", 5.0, C.green], ["APPROVE", 9.35, C.cyan]].forEach(([name, x, color]) => {
    rect(s, x, 2.44, 3.0, 1.06, color);
    text(s, name, x + 0.2, 2.74, 2.6, 0.44, 25, color, { bold: true, align: "center" });
  });
  arrow(s, 4.05, 2.97, 0.75, 0, C.green);
  arrow(s, 8.2, 2.97, 0.95, 0, C.cyan);
  text(s, "Artifacts + tests\n+ constraints", 4.74, 3.76, 3.5, 0.86, 21, C.text, { align: "center" });
  text(s, "Permission for\nthe next action", 9.35, 3.77, 3.04, 0.86, 21, C.text);
  arrow(s, 6.5, 4.72, 0, 0.3, C.coral);
  text(s, "Specific failure → bounded correction", 2.73, 5.17, 6.9, 0.48, 23, C.coral, { bold: true, align: "center" });
  arrow(s, 2.53, 5.38, -0.2, 0, C.coral, false);
  arrow(s, 2.33, 5.38, 0, -1.66, C.coral);
  text(s, "No progress or budget exhausted? Stop / escalate—not “done”.", 0.85, 6.13, 11.58, 0.42, 22, C.amber);
}

// 9. The talk's concepts become actual editable controls.
{
  const s = slide({
    title: "Demo: define the harness",
    subtitle: "Equity fixture: available illustration with synthetic data, not investment advice.",
    timing: "25:00-26:00", speaker: JAMES, segment: "demo",
    explanation: "The local console turns the three practices into editable, validated settings. Framework-native components and application-specific controls remain distinct.",
    talk: "James: this is the same vocabulary you just heard. Switch from All-loaded / observe-only to Progressive / governed: exposure, memory and acceptance change visibly. These settings really reconfigure the next run. Policy and the human boundary never disappear. The live model uses actual tools and loads skills when needed; the framework records the calls. Company, market and portfolio data remain synthetic. Start the governed run now; its prior memory was prepared before the talk.",
    reference: "Launch from demo/agent: ..\\..\\.venv\\Scripts\\python.exe -m equity_event serve; open http://127.0.0.1:8765. Exact implementation: live.py:run_live_episode, create_harness_agent, SkillsProvider.load_skill, scoped FileMemoryProvider, one AgentSession reused across PLAN and EXECUTE. live_config.py supplies editable profiles; ui.py drives the same runtime as CLI. Pin: agent-framework-core==1.18.0; provider agent-framework-openai==1.14.3.\n\nMAF supplies agent/session/history, skill and file-memory providers, native function invocation and OpenTelemetry. Application code supplies synthetic adapters, scope/validation policy, constrained execution, verifier, approval UI and completion certificate. add_tools is experimental. Model code is a validated arithmetic expression in a reviewed Python/HTML/SVG template; python -I is not an OS sandbox. Compaction is off. Fixed goal, policy, no-progress threshold, local telemetry and approval requirements are labeled read-only, not fake controls. The all-loaded profile is observe-only, not unsafe production guidance.\n\nPreflight: run once with the live governed profile and approve to create memory in the stage scope. Prepare a saved live trace and a scripted observe-only near-miss as fallback. A live date failure is not guaranteed. Do not wait through several serial live runs inside this one-minute setup. The old ScriptedEquityClient fixture and its inert exposed_tools metadata remain legacy only; the new console uses actual callable tools.",
    handoff: "James Nguyen switches to the local console and observes the run.",
    refs: ["L", "M1", "M4", "D1", "D2"], source: "[M1] [M4] MAF 1.18.0; progressive tool API experimental. [D1] [D2] Runtime. [L] Synthetic illustration.",
  });
  label(s, "PROGRESSIVE TOOLING", "All loaded → discover / load\nReal executable tools", 0.85, 2.43, 3.63, C.cyan);
  label(s, "CONTEXT HYGIENE", "One session → shared memory\nRecall across episodes", 4.92, 2.43, 3.63, C.violet);
  label(s, "ACCEPTANCE GATES", "Observe → enforce\nBounded correction + approval", 8.99, 2.43, 3.52, C.amber);
  text(s, "MAF 1.18.0: agent · session · skills · memory · native telemetry", 0.85, 4.82, 11.58, 0.53, 23, C.white);
  text(s, "Application: data · execution boundary · policy · checks · console", 0.85, 5.49, 11.58, 0.5, 21, C.text);
  text(s, "Selection never grants permission. Mandatory policy stays on.", 0.85, 6.15, 11.58, 0.39, 21, C.amber);
}

// 10. Original recording, explicitly a fallback with a scripted model.
{
  const s = slide({
    title: "Demo: run and observe",
    subtitle: "Use the local console. Embedded video below is legacy scripted fallback only.",
    timing: "26:00-29:00", speaker: JAMES, segment: "demo",
    explanation: "The live console is the primary demonstration. The unchanged video remains embedded only as an explicitly limited legacy fallback.",
    talk: "James: in the console, expand the MAF trace tree. These are real model and tool spans. Follow load_skill, the newly exposed callable tool, and the memory record from a prior trace. Review the artifact only after acceptance passes; then approve locally. Calls and words can vary because the model is live. A live failure is not promised. The offline seeded example gives a reliable acceptance contrast without pretending its error was spontaneous.",
    reference: "Click path: Progressive / governed → Run harness → Observe → expand load_skill/tool span → inspect prior memory → review dashboard → Approve local result. Warm the same memory scope before the talk. MAF-native spans provide agent/chat/tool parentage, durations, arguments/results and available token usage. Labeled application events supply domain loading/use, memory, acceptance and approval signals in that same trace. If the run exceeds the stage timebox, open the retained trace and identify it as saved live evidence; do not claim a still-running episode completed.\n\nThe original 164.45-second recording is legacy only: prerecorded scripted model, synthetic data and scripted reviewer approval; not a recording of core 1.18, the new console or live model-driven load_skill/tool calls/cross-run memory. Its old loaded label means preselection. It remains a last-resort fallback and is not investment advice. Foundry gpt-4o-mini-tts / onyx narration is unchanged. Use either the console story or full video playback, not both. Re-recording would be useful after this implementation; no new recording was created.",
    handoff: "James Nguyen uses the final minute to contrast live evidence with the explicitly seeded acceptance example.",
    refs: ["D1", "D2", "D3", "M5"], source: "[D1] [D2] Live console/runtime. [D3] Native MAF + application telemetry. [M5] Legacy video: 164.45 s.",
  });
  s.addMedia({
    type: "video", path: video, cover: `data:image/png;base64,${fs.readFileSync(cover).toString("base64")}`,
    x: 0.75, y: 1.85, w: 8.64, h: 4.86, objectName: "Narrated Equity Event Harness Demo",
  });
  text(s, "IN THE CONSOLE", 9.85, 2.1, 2.55, 0.42, 19, C.cyan, { bold: true });
  text(s, "Real tool spans\n\nOn-demand skills\n\nMemory + gates", 9.85, 2.89, 2.55, 2.71, 22, C.text, { valign: "top" });
  text(s, "Video predates\nthese capabilities", 9.85, 5.92, 2.55, 0.67, 17, C.amber);
}

// 11. One concrete definition-to-trace example, not a finance result slide.
{
  const s = slide({
    title: "Demo: prove loading, recall and acceptance",
    subtitle: "Native MAF spans show activity. Application checks decide what it means.",
    timing: "29:00-30:00", speaker: JAMES, segment: "demo",
    explanation: "The final minute separates live tool/loading/recall evidence from a deterministic seeded acceptance demonstration. Both use the same runtime and telemetry.",
    talk: "James: the live trace proves the model loaded a skill and invoked a tool. Cross-run recall names the earlier trace; it is not memory we invented in narration. Now inspect the explicitly scripted near-miss: observe-only says preview done while event_date_alignment is false; strict mode requests correction. The defect is seeded, the execution and checks are real. Approval remains separate. No model autonomously rewrites policy. Close the prepared material at 30:00.",
    reference: "Evidence landmarks: demo/live-evidence, each run's telemetry.json and runtime-state.json; native execute_tool/load_skill span and function call ID; application skill_loaded then skill_used; memory_read and cross_run_memory_recalled with source_trace_id; memory_written after approval. MAF emits invocation spans; custom semantics are labeled application. The exact real trace IDs are listed in retained evidence, not hardcoded in slides.\n\nFor a reliable near-miss choose Scripted / offline, set Acceptance gates to Observe only, Run harness: seeded event_date_alignment false yields unverified_preview, no certificate. Switch to Strict and rerun: bounded_correction_requested, corrected pass, then separate approval. These offline runs use real MAF function execution, not a live model. If a complete two-profile comparison would overrun, inspect prepared saved traces instead and call them saved. Do not expect the live model to fail. Ordering, counts, wording, token usage and latency vary. No autonomous lesson promotion or extra finance section follows.",
    handoff: "James Nguyen → James Nguyen, Alexandre Delarue and Kunwarpreet Behar: prepared content ends at 30:00; begin discussion.",
    refs: ["D1", "D2", "D3"], source: "[D2] MAF skill/memory providers. [D3] Retained traces; offline date defect explicitly seeded. Synthetic data.",
  });
  text(s, "LIVE MODEL EVIDENCE", 0.85, 2.27, 5.3, 0.46, 23, C.cyan, { bold: true });
  text(s, "load_skill → tool invocation", 0.85, 2.98, 5.4, 0.47, 23, C.white);
  text(s, "cross_run_memory_recalled\nsource_trace_id → earlier episode", 0.85, 3.75, 5.35, 0.95, 20, C.text);
  arrow(s, 6.33, 3.45, 0.42, 0, C.muted);
  text(s, "SEEDED OFFLINE NEAR-MISS", 7.1, 2.27, 5.22, 0.46, 22, C.amber, { bold: true });
  text(s, "Observe only ≠ verified", 7.1, 2.98, 5.22, 0.47, 22, C.white);
  text(s, "code: event_date_alignment\npassed: false", 7.1, 3.75, 5.22, 0.95, 20, C.text, { fontFace: "Consolas" });
  text(s, "runtime-state.json → bounded_correction_requested", 0.85, 5.45, 11.58, 0.46, 23, C.green);
  text(s, "Define → run → observe. Prepared content ends here.", 0.85, 6.12, 11.58, 0.44, 23, C.white);
}

// 12. Discussion is not a hidden additional lecture.
{
  const s = slide({
    title: "Where do your agents struggle?",
    subtitle: "Discussion · proposed 30:00–45:00 slot, adjusted to the usable session time",
    timing: "30:00-45:00", speaker: ALL, segment: "discussion",
    explanation: "Three prompts invite real cases. The 15-minute slot is the deck's proposed allocation, adjusted to the actual remaining time.",
    talk: "All three presenters facilitate; this is discussion, not prepared lecture. The 15-minute discussion slot is our proposed allocation after 30 minutes of prepared content including the five-minute demo. Use the actual remaining time, and do not fill it with a hidden advanced-research section.\n\nInvite one concrete case: what was the goal, where did behavior diverge, and what evidence showed the problem? Kunwarpreet can probe tool overload or lost constraints; Alexandre can probe bounded autonomy, acceptance and approval; James can connect the question to configuration and trace examples. Separate missing capability from poor selection, lost context from bad evidence, and false success from denied permission. Let participants compare constraints and tradeoffs; avoid immediately prescribing a new framework.\n\nUse the final available minute to name one practical control a participant will try and one observable signal for whether it helped. If joining or discussion began late, prioritize a useful case rather than hitting a nominal 45-minute lecture endpoint.",
    handoff: "James Nguyen, Alexandre Delarue and Kunwarpreet Behar close the discussion when usable session time ends. References remain untimed.",
    refs: ["L"], source: "[L] The 15-minute discussion slot is a proposed delivery allocation.",
  });
  label(s, "TOOL OVERLOAD", "What is available that\nrarely helps the next step?", 0.85, 2.53, 3.63, C.cyan);
  label(s, "CONTEXT DRIFT", "Where does the goal\nor a constraint get lost?", 4.92, 2.53, 3.63, C.violet);
  label(s, "ACCEPTANCE FAILURE", "What was called “done”\nbefore the job was correct?", 8.99, 2.53, 3.52, C.amber);
  text(s, "Bring one case: goal → failure → observable evidence.", 0.85, 5.52, 11.6, 0.69, 27, C.white, { bold: true });
}

// 13. Sources, without another teaching section.
{
  const s = slide({
    title: "Primary sources and demonstration boundaries",
    subtitle: "Public design references, actual code/artifacts, and clear demonstration limits.",
    timing: "45:00 / untimed references", speaker: ALL, segment: "references",
    explanation: "The reference map separates public product behavior, local demonstration evidence and presentation choices. Exact allocations and the synthetic fixture are not universal requirements.",
    talk: "Untimed reference slide only. Public URLs support context curation, progressive tooling, durable state, verification and the pinned framework composition. Repository evidence distinguishes live model traces from seeded offline and legacy media. The synthetic fixture is an available illustration, not investment advice. The 30+15 allocation and speaker map are delivery choices. Broader research remains outside the prepared talk.",
    handoff: "James Nguyen, Alexandre Delarue and Kunwarpreet Behar: end; no further prepared material.",
    refs: Object.keys(sources),
    source: "Full public URLs and precise claims are in notes. Synthetic evidence and proposed delivery choices are labeled.",
  });
  const groups = [
    { x: 0.85, color: C.blue, title: "PUBLIC GUIDANCE", lines: [
      "[V1] Context engineering", "[V2] Tool Search", "[V3] Managed sessions", "[V4] Long-running harnesses", "[M1] [M4] Framework 1.18",
    ], bottom: "Patterns and pinned behavior.\nNo universal performance claim." },
    { x: 4.93, color: C.cyan, title: "ACTUAL DEMO EVIDENCE", lines: [
      "[D1] Console + live runtime", "[D2] Skill loading + memory", "[D3] Native spans + app events", "[M5] Legacy video fallback",
    ], bottom: "Live ≠ scripted ≠ saved evidence.\nSynthetic data; local-only output." },
    { x: 9.01, color: C.amber, title: "DELIVERY BOUNDARY", lines: [
      "[L] Presentation choices", "30 minutes prepared content", "Five-minute harness demo", "Exact timing + available fixture",
    ], bottom: "Synthetic illustration only.\n30+15 is a proposed allocation." },
  ];
  groups.forEach((g) => {
    text(s, g.title, g.x, 2.15, 3.55, 0.51, 19, g.color, { bold: true });
    arrow(s, g.x, 2.84, 3.5, 0, C.line, false);
    g.lines.forEach((item, i) => text(s, item, g.x, 3.06 + i * 0.51, 3.55, 0.43, 18, C.text));
    text(s, g.bottom, g.x, 5.94, 3.55, 0.69, 16, C.muted);
  });
}

async function main() {
  if (count !== 13) throw new Error(`Expected 13 slides, found ${count}`);
  await pptx.writeFile({ fileName: OUT });
}
main().catch((error) => {
  console.error(error);
  process.exit(1);
});
