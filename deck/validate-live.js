"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { isDeepStrictEqual } = require("node:util");

const ROLES = ["warmup", "recall", "all_loaded", "seeded_observe", "seeded_strict"];
const CHECKS = [
  "script_execution", "independent_recalculation", "approved_method", "claim_provenance",
  "required_sections", "restricted_data_excluded", "causal_claim_guard",
  "chart_data_integrity", "event_date_alignment",
];
const SOURCES = [
  "public-sources.json", "market-prices.json", "internal-portfolio.json",
  "internal-policy.json", "internal-thesis.json", "lessons.json",
];
const TOOL_SKILLS = {
  public_source_search: ["financial-source-retrieval"],
  internal_api_lookup: ["financial-source-retrieval"],
  execute_analysis: ["abnormal-return-model", "event-date-alignment", "interactive-briefing"],
};
const EVENT_META = new Set([
  "id", "sequence", "event", "at", "timestamp", "timestamp_unix_nano",
  "trace_id", "span_id", "parent_span_id", "origin",
]);
const REDACTED = /^(?:\[REDACTED(?: URL)?\]|\[CONTENT DISABLED\]|<redacted>)$/i;

function demand(condition, message) {
  if (!condition) throw new Error(`Live evidence: ${message}`);
}

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function same(actual, expected, message) {
  demand(isDeepStrictEqual(actual, expected), message);
}

function hash(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function json(text, label) {
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Live evidence: invalid JSON in ${label}`);
  }
}

function safePath(base, relative, kind = "file") {
  demand(typeof relative === "string" && relative.length > 0, "missing artifact path");
  const parts = relative.split(/[\\/]/);
  demand(parts.every((part) => /^[A-Za-z0-9_.-]+$/.test(part) && part !== "." && part !== ".."),
    `unsafe artifact path: ${relative}`);
  let resolved = base;
  for (const part of parts) {
    resolved = path.join(resolved, part);
    demand(fs.existsSync(resolved), `missing required ${kind}: ${relative}`);
    demand(!fs.lstatSync(resolved).isSymbolicLink(), `symlink artifact is not allowed: ${relative}`);
  }
  const stat = fs.statSync(resolved);
  demand(kind === "directory" ? stat.isDirectory() : stat.isFile(), `invalid ${kind}: ${relative}`);
  return resolved;
}

function readJson(base, relative) {
  const value = json(fs.readFileSync(safePath(base, relative), "utf8"), relative);
  inspectPrivacy(value, relative);
  return value;
}

function secretKey(key) {
  const leaf = key.split(".").pop().replace(/[^a-z0-9]/gi, "").toLowerCase();
  if (/^(?:(?:input|output|total|max|cached|reasoning|cachecreation|cacheread)(?:completion)?tokens?|(?:input|output|total)tokencount)$/.test(leaf)) return false;
  const normalized = key.replace(/[^a-z0-9]/gi, "").toLowerCase();
  return /authorization|authentication|apikey|accesskey|accountkey|credential|password|passwd|secret|cookie|privatekey|connectionstring|(?:request|response)?headers?/.test(normalized)
    || /^(?:auth|token|accesstoken|refreshtoken|idtoken|bearer)$/.test(leaf);
}

function inspectPrivacy(value, location, depth = 0) {
  demand(depth < 70, `excessively nested evidence in ${location}`);
  if (Array.isArray(value)) {
    value.forEach((item, index) => inspectPrivacy(item, `${location}[${index}]`, depth + 1));
  } else if (object(value)) {
    for (const [key, item] of Object.entries(value)) {
      const schemaProperty = object(item) && ("type" in item || "description" in item || "$ref" in item);
      demand(!secretKey(key) || item == null || item === "" || REDACTED.test(String(item)) || schemaProperty,
        `credential/header field in ${location}.${key}`);
      inspectPrivacy(item, `${location}.${key}`, depth + 1);
    }
  } else if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      let structured;
      try { structured = JSON.parse(value); } catch { /* Non-JSON skill prose is expected. */ }
      if (structured !== undefined) inspectPrivacy(structured, `${location}:json`, depth + 1);
    }
    demand(!/\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}/i.test(value)
      && !/\bsk-[A-Za-z0-9_-]{16,}\b/.test(value)
      && !/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/.test(value),
    `credential value in ${location}`);
    const assignments = value.matchAll(/\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*["']?([A-Za-z0-9_+./=-]{12,})/gi);
    for (const match of assignments) {
      demand(!match[1] || /^(?:string|REDACTED|your[_-]|example|placeholder)/i.test(match[1]),
        `credential assignment in ${location}`);
    }
    for (const match of value.matchAll(/https?:\/\/[^\s<>"'\\]+/gi)) {
      let url;
      try { url = new URL(match[0]); } catch { continue; }
      demand(!url.username && !url.password, `credential-bearing URL in ${location}`);
      demand(!(
        /^(?:teams\.microsoft\.com|teams\.live\.com|meet\.google\.com)$/i.test(url.hostname)
        || /(?:^|\.)zoom\.us$/i.test(url.hostname) && /^\/[js]\//.test(url.pathname)
      ), `private meeting URL in ${location}`);
      for (const [key, content] of url.searchParams) {
        demand(!secretKey(key) || REDACTED.test(content), `credential URL parameter in ${location}`);
      }
    }
  }
}

function instant(value, label) {
  demand(typeof value === "string", `missing timestamp: ${label}`);
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{1,9})Z$/.exec(value);
  demand(match && Number.isFinite(Date.parse(`${match[1]}Z`)), `invalid timestamp: ${label}`);
  return BigInt(Date.parse(`${match[1]}Z`)) * 1_000_000n + BigInt(match[2].padEnd(9, "0"));
}

function parseArguments(value, label) {
  // MAF 1.18 serializes zero observable arguments as "None", not "{}".
  const parsed = value === "None" ? {} : typeof value === "string" ? json(value, label) : value;
  demand(object(parsed), `invalid tool arguments: ${label}`);
  return parsed;
}

function structured(value) {
  if (Array.isArray(value)) return value.map(structured);
  if (object(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, structured(item)]));
  if (typeof value === "string" && /^[\s]*[{[]/.test(value)) {
    let parsed;
    try { parsed = JSON.parse(value); } catch { return value; }
    return structured(parsed);
  }
  return value;
}

function eventDetails(event) {
  return Object.fromEntries(Object.entries(event).filter(([key]) => !EVENT_META.has(key)));
}

function validateTrace(run) {
  const { telemetry: t, role } = run;
  demand(t.schema_version === 1 && t.capture_content === true, `${role}: native content capture is missing`);
  demand(/^[a-f0-9]{32}$/.test(t.trace_id) && !/^0+$/.test(t.trace_id), `${role}: invalid trace ID`);
  demand(Array.isArray(t.spans) && t.spans.length > 3 && Array.isArray(t.events), `${role}: missing native spans/events`);
  const spans = new Map();
  const nativeEvents = new Map();
  for (const span of t.spans) {
    demand(/^[a-f0-9]{16}$/.test(span.span_id) && !/^0+$/.test(span.span_id) && !spans.has(span.span_id),
      `${role}: invalid or duplicate span ID`);
    demand(span.trace_id === t.trace_id, `${role}: cross-trace span leakage`);
    demand(object(span.attributes) && Array.isArray(span.events), `${role}: invalid span attributes/events`);
    const start = instant(span.start_time, span.name);
    const end = instant(span.end_time, span.name);
    demand(end >= start && Number.isFinite(span.duration_ms)
      && Math.abs(span.duration_ms - Number(end - start) / 1e6) < 0.001, `${role}: invalid span duration`);
    demand(["UNSET", "OK", "ERROR"].includes(span.status?.code), `${role}: invalid native span status`);
    demand(span.dropped_attributes === 0 && span.dropped_events === 0, `${role}: dropped native evidence`);
    const operation = span.attributes["gen_ai.operation.name"];
    if (operation) {
      demand(["invoke_agent", "chat", "execute_tool"].includes(operation), `${role}: unsupported native operation`);
      demand(span.origin === "maf" && span.instrumentation_scope?.name === "agent_framework"
        && span.instrumentation_scope?.version === "1.18.0", `${role}: missing authentic native MAF origin/scope`);
    } else {
      demand(span.origin === "application" && span.instrumentation_scope?.name === "equity_event.live_harness"
        && span.name === "equity_event.episode", `${role}: unsupported application span`);
    }
    spans.set(span.span_id, span);
    for (const event of span.events) {
      const time = instant(event.timestamp, event.name);
      demand(time >= start && time <= end, `${role}: span event outside its parent lifetime`);
      if (event.attributes?.["harness.origin"] !== "application") continue;
      const id = event.attributes["harness.event.id"];
      demand(event.origin === "application" && !nativeEvents.has(id), `${role}: duplicate/mislabeled application event`);
      nativeEvents.set(id, { event, span });
    }
  }
  const roots = t.spans.filter((span) => span.parent_span_id === null);
  demand(roots.length === 1 && roots[0].origin === "application", `${role}: missing unique episode root`);
  for (const span of t.spans) {
    if (span === roots[0]) continue;
    const parent = spans.get(span.parent_span_id);
    demand(parent && parent !== span, `${role}: orphaned native span parent`);
    demand(instant(span.start_time) >= instant(parent.start_time)
      && instant(span.end_time) <= instant(parent.end_time), `${role}: span escapes parent lifetime`);
    const visited = new Set([span.span_id]);
    let ancestor = parent;
    while (ancestor !== roots[0]) {
      demand(ancestor && !visited.has(ancestor.span_id), `${role}: cyclic/broken span parentage`);
      visited.add(ancestor.span_id);
      ancestor = spans.get(ancestor.parent_span_id);
    }
  }
  let previous = 0n;
  t.events.forEach((event, index) => {
    demand(event.sequence === index + 1 && event.id === `${t.trace_id}:${String(index + 1).padStart(6, "0")}`,
      `${role}: nonmonotonic application event ID`);
    const original = nativeEvents.get(event.id);
    demand(original, `${role}: application event has no OTel source`);
    demand(event.origin === "application" && event.trace_id === t.trace_id
      && event.span_id === original.span.span_id && event.parent_span_id === original.span.parent_span_id,
    `${role}: fabricated application event parentage`);
    same(eventDetails(event), json(original.event.attributes["harness.event.details"], event.id),
      `${role}: application event disagrees with OTel source details`);
    demand(event.event === original.event.name && event.sequence === original.event.attributes["harness.event.sequence"]
      && event.timestamp === original.event.timestamp && event.at === event.timestamp,
    `${role}: application event disagrees with OTel source metadata`);
    const time = instant(event.at);
    demand(time > previous, `${role}: application events are out of order`);
    previous = time;
  });
  demand(nativeEvents.size === t.events.length, `${role}: application events omitted from projection`);
  run.spans = spans;
  run.rootSpan = roots[0];
  run.events = (name) => t.events.filter((event) => event.event === name);
  run.chats = t.spans.filter((span) => span.attributes["gen_ai.operation.name"] === "chat");
  run.agents = t.spans.filter((span) => span.attributes["gen_ai.operation.name"] === "invoke_agent");
  run.tools = t.spans.filter((span) => span.attributes["gen_ai.operation.name"] === "execute_tool");
  demand(run.chats.length && run.agents.length >= 2 && run.tools.length, `${role}: agent/chat/tool span layer is missing`);
}

function validateCalls(run) {
  const { role, chats, tools, spans, config } = run;
  const issued = new Map();
  const toolCalls = new Map();
  const nativeRejections = new Set();
  for (const chat of chats) {
    demand(spans.get(chat.parent_span_id)?.attributes["gen_ai.operation.name"] === "invoke_agent",
      `${role}: chat is not a native agent child`);
    if (config.model === "live") {
      demand(chat.attributes["gen_ai.request.model"] === "gpt-5.6-terra"
        && chat.attributes["gen_ai.provider.name"] === "azure.ai.openai"
        && /^gpt-5\.6-terra(?:-|$)/.test(chat.attributes["gen_ai.response.model"] || ""),
      `${role}: native live deployment/provider mismatch`);
      for (const key of ["gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"]) {
        demand(Number.isInteger(chat.attributes[key]) && chat.attributes[key] >= 0, `${role}: missing native token usage`);
      }
    } else {
      demand(chat.attributes["gen_ai.provider.name"] === "scripted", `${role}: seeded execution misrepresented as live`);
    }
    const input = json(chat.attributes["gen_ai.input.messages"], `${role}: native chat input`);
    const output = json(chat.attributes["gen_ai.output.messages"], `${role}: native chat output`);
    demand(Array.isArray(input) && Array.isArray(output) && input.length && output.length, `${role}: native messages are missing`);
    for (const part of input.flatMap((message) => message.parts || [])) {
      if (part.type === "tool_call_response" && typeof part.response === "string" && part.response.startsWith("Error:")) {
        nativeRejections.add(part.id);
      }
    }
    for (const message of output) {
      if (message.role !== "assistant") continue;
      demand(Array.isArray(message.parts), `${role}: malformed assistant message parts`);
      for (const part of message.parts.filter((item) => item.type === "tool_call")) {
        demand(typeof part.id === "string" && part.id && !issued.has(part.id) && typeof part.name === "string",
          `${role}: duplicate/missing model-issued call ID`);
        issued.set(part.id, { chat, name: part.name, arguments: parseArguments(part.arguments, part.id) });
      }
    }
  }
  for (const tool of tools) {
    const attrs = tool.attributes;
    const call = attrs["gen_ai.tool.call.id"];
    const model = issued.get(call);
    demand(model && !toolCalls.has(call), `${role}: native tool has no unique model-issued call ID`);
    demand(model.name === attrs["gen_ai.tool.name"] && tool.name === `execute_tool ${model.name}`,
      `${role}: native tool name differs from model-issued call`);
    demand(tool.parent_span_id === model.chat.parent_span_id && instant(tool.start_time) >= instant(model.chat.end_time),
      `${role}: native tool is not ordered under its issuing agent`);
    same(parseArguments(attrs["gen_ai.tool.call.arguments"], call), model.arguments,
      `${role}: native tool arguments differ from model-issued call`);
    demand(tool.status.code === "ERROR" || typeof attrs["gen_ai.tool.call.result"] === "string"
      && attrs["gen_ai.tool.call.result"].length > 0, `${role}: native tool result is missing`);
    toolCalls.set(call, tool);
  }
  const savedFailures = new Set((run.session.state?.in_memory?.messages || [])
    .flatMap((message) => message.contents || [])
    .filter((content) => content.type === "function_result" && typeof content.exception === "string" && content.exception.length)
    .map((content) => content.call_id));
  for (const [call] of issued) {
    // MAF validates arguments before it opens execute_tool. Retain that honest
    // distinction rather than demanding or inventing a span for a rejected call.
    demand(toolCalls.has(call) || run.events("control_rejected").some((event) => event.call_id === call)
      || nativeRejections.has(call) && savedFailures.has(call),
      `${role}: model-issued call lacks native execution or explicit rejection`);
  }
  for (const name of ["record_plan", "get_episode_state", "public_source_search", "internal_api_lookup", "execute_analysis", "verify_analysis"]) {
    demand(tools.some((tool) => tool.attributes["gen_ai.tool.name"] === name && tool.status.code !== "ERROR"),
      `${role}: missing native ${name} execution`);
  }
  run.toolCalls = toolCalls;
  run.nativeTool = (event, name) => {
    const tool = event.call_id ? toolCalls.get(event.call_id) : spans.get(event.span_id);
    demand(tool?.attributes["gen_ai.tool.name"] === name && tool.status.code !== "ERROR",
      `${role}: ${event.event} is unsupported by native ${name}`);
    return tool;
  };
}

function validateSession(run) {
  const { role, state, session, config } = run;
  demand(state.run?.trace_id === run.telemetry.trace_id && state.run.idempotency_key === run.id,
    `${role}: runtime identity does not match native trace`);
  demand(Array.isArray(state.events) && state.events.length === run.telemetry.events.length, `${role}: runtime event mirror mismatch`);
  state.events.forEach((event, index) => {
    same({ ...event, at: undefined }, { ...eventDetails(run.telemetry.events[index]), event: run.telemetry.events[index].event, at: undefined },
      `${role}: runtime event disagrees with native evidence`);
  });
  const starts = run.events("conversation_turn_started");
  const sessions = run.events("session_started");
  demand(starts.length === 2 && sessions.length === 1 && starts[0].phase === "plan" && starts[1].phase === "execute",
    `${role}: missing plan/execute two-turn episode`);
  demand(typeof session.session_id === "string" && session.session_id.length > 0
    && [...starts, ...sessions].every((event) => event.session_id === session.session_id),
  `${role}: two turns do not share the saved AgentSession`);
  demand(new Set(run.agents.map((span) => span.attributes["gen_ai.agent.id"])).size === 1,
    `${role}: native turns used different agents`);
  const finished = run.events("conversation_turn_finished");
  for (const start of starts) {
    const finish = finished.filter((event) => event.phase === start.phase).at(-1);
    demand(finish && finish.sequence > start.sequence && run.agents.some((span) =>
      instant(span.start_time) >= instant(start.at) && instant(span.end_time) <= instant(finish.at)),
    `${role}: ${start.phase} turn has no enclosed native agent invocation`);
  }
  const savedCalls = new Map();
  const history = session.state?.in_memory?.messages;
  demand(config.model !== "live" || Array.isArray(history), `${role}: saved native session history is missing`);
  for (const message of history || []) {
    for (const content of message.contents || []) {
      if (message.role === "assistant" && content.type === "function_call") savedCalls.set(content.call_id, content);
    }
  }
  for (const [call, tool] of run.toolCalls) {
    if (!history) continue;
    const saved = savedCalls.get(call);
    demand(saved?.name === tool.attributes["gen_ai.tool.name"], `${role}: native call missing from saved AgentSession`);
    same(structured(parseArguments(saved.arguments, call)), structured(parseArguments(tool.attributes["gen_ai.tool.call.arguments"], call)),
      `${role}: saved session call arguments differ from native span`);
  }
  const started = run.events("episode_started");
  demand(started.length === 1, `${role}: missing episode metadata`);
  same(started[0].config, config, `${role}: started configuration mismatch`);
}

function validateSkills(run, repoRoot) {
  const { role, config } = run;
  const discovery = run.events("skill_catalog_discovered");
  demand(discovery.length === 1 && discovery[0].content_level === "names_and_purposes",
    `${role}: skill discovery must be metadata only`);
  same(discovery[0].skills.map((skill) => skill.name).sort(), [...config.available_skills].sort(),
    `${role}: discovered skill catalog mismatch`);
  const catalog = new Set(config.available_skills);
  const loaded = run.events("skill_loaded");
  const selected = run.events("skill_selected");
  const preloaded = run.events("skill_preloaded");
  const firstChat = run.chats[0];
  const nativeInput = [
    ...json(firstChat.attributes["gen_ai.system_instructions"] || "[]", "native instructions"),
    ...json(firstChat.attributes["gen_ai.input.messages"], "native input").flatMap((message) => message.parts),
  ].map((part) => part.content || "").join("\n");
  if (config.skill_mode === "all_loaded") {
    demand(!loaded.length && !selected.length && preloaded.length === catalog.size
      && !run.tools.some((tool) => tool.attributes["gen_ai.tool.name"] === "load_skill"),
    `${role}: all-loaded profile is not genuinely preloaded`);
    same(preloaded.map((event) => event.skill).sort(), [...catalog].sort(), `${role}: incomplete preloaded catalog`);
    for (const event of preloaded) {
      const source = fs.readFileSync(safePath(repoRoot, `demo/agent/skills/${event.skill}/SKILL.md`), "utf8").replace(/\r\n/g, "\n");
      demand(event.phase === "before_model" && instant(event.at) < instant(firstChat.start_time)
        && event.bytes === Buffer.byteLength(source) && nativeInput.includes(source),
      `${role}: preload not supported by actual native model input`);
    }
  } else {
    demand(config.skill_mode === "progressive" && !preloaded.length && loaded.length > 0,
      `${role}: missing progressive native skill loading`);
    for (const event of selected) {
      demand(catalog.has(event.skill) && discovery[0].sequence < event.sequence, `${role}: selection precedes discovery/uses unsupported skill`);
      demand(loaded.some((load) => load.call_id === event.call_id && load.skill === event.skill)
        || run.events("control_rejected").some((failure) => failure.call_id === event.call_id),
      `${role}: skill selection has no successful load or rejection`);
    }
    for (const event of loaded) {
      demand(catalog.has(event.skill), `${role}: unsupported loaded skill`);
      const tool = run.nativeTool(event, "load_skill");
      const result = tool.attributes["gen_ai.tool.call.result"];
      const args = parseArguments(tool.attributes["gen_ai.tool.call.arguments"], event.call_id);
      const source = fs.readFileSync(safePath(repoRoot, `demo/agent/skills/${event.skill}/SKILL.md`), "utf8").replace(/\r\n/g, "\n");
      demand(args.skill_name === event.skill && result.startsWith(source.trimEnd())
        && hash(result) === event.content_sha256 && Buffer.byteLength(result) === event.bytes,
      `${role}: native loaded skill result/hash mismatch`);
      const selection = selected.find((item) => item.skill === event.skill && item.call_id === event.call_id);
      demand(selection && selection.sequence < event.sequence
        && instant(selection.at) <= instant(tool.start_time) && instant(event.at) >= instant(tool.end_time),
      `${role}: skill selection/load order is unsupported by native execution`);
    }
  }
  const used = run.events("skill_used");
  demand(used.length > 0, `${role}: missing skill usage evidence`);
  for (const event of used) {
    demand(TOOL_SKILLS[event.tool]?.includes(event.skill), `${role}: unsupported skill/tool usage claim`);
    const tool = run.nativeTool(event, event.tool);
    demand([...loaded, ...preloaded].some((load) => load.skill === event.skill && load.sequence < event.sequence),
      `${role}: skill use has no preceding content load`);
    demand(instant(event.at) >= instant(tool.end_time), `${role}: skill usage claims precede native execution`);
  }
  for (const tool of run.tools) {
    if (tool.status.code === "ERROR") continue;
    for (const skill of TOOL_SKILLS[tool.attributes["gen_ai.tool.name"]] || []) {
      demand(used.some((event) => event.skill === skill && event.call_id === tool.attributes["gen_ai.tool.call.id"]),
        `${role}: successful native tool lacks skill usage evidence`);
    }
  }
}

function validateReport(report, label) {
  demand(report?.verifier_version === "equity-verifier/1.1" && Array.isArray(report.checks),
    `${label}: missing verifier result`);
  same(report.checks.map((check) => check.code).sort(), [...CHECKS].sort(), `${label}: expected nine distinct verifier checks`);
  demand(report.checks.every((check) => typeof check.passed === "boolean")
    && report.passed === report.checks.every((check) => check.passed), `${label}: inconsistent verifier pass result`);
}

function validateSources(run, root) {
  const sources = run.ledger.sources;
  demand(Array.isArray(sources), `${run.role}: missing source evidence ledger`);
  if (run.role !== "seeded_observe" || sources.length) {
    same(sources.map((source) => source.artifact).sort(), SOURCES.map((name) => `demo/sample-input/${name}`).sort(),
      `${run.role}: required source snapshots missing`);
    demand(new Set(sources.map((source) => source.source_id)).size === SOURCES.length, `${run.role}: duplicate source identities`);
  }
  for (const source of sources) {
    demand(source.classification === "synthetic-illustrative"
      && hash(fs.readFileSync(safePath(root, source.artifact))) === source.content_sha256,
    `${run.role}: source content hash mismatch: ${source.artifact}`);
  }
  const admitted = run.events("policy_admission");
  demand(admitted.length === 1 && admitted[0].never_deferred === true, `${run.role}: mandatory policy admission missing`);
  same(admitted[0].decision, run.policy, `${run.role}: policy admission mismatch`);
  demand(run.policy.approval_required === true && run.policy.decision === "allow_after_approval", `${run.role}: required approval policy changed`);
  const retrieval = run.events("sources_retrieved");
  demand(retrieval.some((event) => event.adapter === "public-snapshot")
    && retrieval.some((event) => event.adapter === "mock-internal-api"), `${run.role}: missing public/internal retrieval`);
  for (const event of retrieval) {
    const name = event.adapter === "public-snapshot" ? "public_source_search" : "internal_api_lookup";
    run.nativeTool(event, name);
  }
  const publicSource = readJson(root, "demo/sample-input/public-sources.json");
  const market = readJson(root, "demo/sample-input/market-prices.json");
  const resources = new Set();
  for (const tool of run.tools) {
    const name = tool.attributes["gen_ai.tool.name"];
    if (!["public_source_search", "internal_api_lookup"].includes(name) || tool.status.code === "ERROR") continue;
    const result = json(tool.attributes["gen_ai.tool.call.result"], `${run.role}: native retrieval result`);
    if (name === "public_source_search") {
      const claims = publicSource.sources.flatMap((source) => source.claims
        .filter((claim) => run.policy.admitted_claim_ids.includes(claim.claim_id))
        .map((claim) => ({ ...claim, source_id: source.source_id, integrity: source.integrity, confidentiality: source.confidentiality })));
      same(result, { event: publicSource.event, market, claims }, `${run.role}: native public retrieval differs from hashed source`);
    } else {
      const args = parseArguments(tool.attributes["gen_ai.tool.call.arguments"], "native internal retrieval");
      demand(["policy", "portfolio", "thesis", "lessons"].includes(args.resource), `${run.role}: unsupported retrieved resource`);
      resources.add(args.resource);
      const source = readJson(root, `demo/sample-input/${args.resource === "lessons" ? "lessons" : `internal-${args.resource}`}.json`);
      const position = args.resource === "portfolio" ? source.positions.find((item) => item.ticker === market.ticker) : null;
      const data = position ? { ticker: position.ticker, exposure_band: position.exposure_band } : source;
      same(result, { classification: "synthetic-illustrative", resource: args.resource, data },
        `${run.role}: native internal retrieval differs from hashed/redacted source`);
    }
  }
  same([...resources].sort(), ["lessons", "policy", "portfolio", "thesis"], `${run.role}: missing required native internal retrieval`);
}

function validateAcceptance(run, root) {
  const { role, directory: dir, result, config } = run;
  const market = readJson(root, "demo/sample-input/market-prices.json");
  const event = readJson(root, "demo/sample-input/public-sources.json").event;
  demand(event.market_session === "after_close" && market.adjusted === true, "unsupported synthetic event/price fixture");
  const requiredDate = market.rows.find((row) => row.date > event.announced_at.slice(0, 10))?.date;
  const evaluated = run.events("acceptance_evaluated");
  demand(evaluated.length > 0, `${role}: missing independent acceptance`);
  const attempts = [];
  for (const evaluation of evaluated) {
    const number = evaluation.attempt;
    demand(Number.isInteger(number) && number === attempts.length + 1 && number <= config.max_execution_attempts,
      `${role}: invalid execution attempt sequence/budget`);
    const attempt = `attempt-${String(number).padStart(2, "0")}`;
    const report = readJson(dir, `verification-${number}.json`);
    validateReport(report, role);
    same(evaluation.report, report, `${role}: acceptance event differs from retained verifier`);
    const verifier = run.nativeTool(evaluation, "verify_analysis");
    same(json(verifier.attributes["gen_ai.tool.call.result"], "native verifier result"), report,
      `${role}: native verifier result mismatch`);
    const analysis = readJson(dir, `${attempt}/analysis.json`);
    const script = safePath(dir, `${attempt}/generated_analysis.py`);
    const dashboard = safePath(dir, `${attempt}/dashboard.html`);
    const executed = run.events("analysis_executed").find((item) => item.attempt === number);
    const proposed = run.events("analysis_proposed").find((item) => item.attempt === number);
    demand(executed && proposed && proposed.sequence < executed.sequence && executed.sequence < evaluation.sequence,
      `${role}: missing native execution before acceptance`);
    const tool = run.nativeTool(executed, "execute_analysis");
    demand(proposed.span_id === tool.span_id, `${role}: analysis proposal is detached from native execution`);
    const args = parseArguments(tool.attributes["gen_ai.tool.call.arguments"], "execution arguments");
    same(json(tool.attributes["gen_ai.tool.call.result"], "execution result"), executed.result,
      `${role}: native analysis result differs from execution event`);
    demand(executed.result.success === true && executed.result.return_code === 0 && executed.result.stderr === "",
      `${role}: analysis did not execute successfully`);
    demand(args.event_date === analysis.event_date && args.event_date === proposed.event_date
      && args.return_expression === proposed.return_expression, `${role}: analysis does not match model-issued execution`);
    const index = market.rows.findIndex((row) => row.date === analysis.event_date);
    demand(index > 0 && analysis.data_classification === "synthetic-illustrative"
      && analysis.method?.benchmark === market.benchmark && analysis.method.benchmark_adjusted === true
      && analysis.method.prices_adjusted === true, `${role}: invalid analysis method/date`);
    const security = market.rows[index][market.ticker] / market.rows[index - 1][market.ticker] - 1;
    const benchmark = market.rows[index][market.benchmark] / market.rows[index - 1][market.benchmark] - 1;
    for (const [key, expected] of Object.entries({ security, benchmark, abnormal: security - benchmark })) {
      demand(Number.isFinite(analysis.returns?.[key]) && Math.abs(analysis.returns[key] - expected) < 1e-12,
        `${role}: independent ${key} recomputation mismatch`);
    }
    demand(report.checks.find((check) => check.code === "event_date_alignment").passed === (analysis.event_date === requiredDate),
      `${role}: verifier hides a real event-date error`);
    attempts.push({ report, analysis, script, dashboard, prefix: attempt, evaluation });
  }
  const final = attempts.at(-1);
  if (role === "seeded_observe") {
    demand(config.gate_mode === "observe" && !final.report.passed && result.status === "unverified_preview"
      && result.certified === false && !result.certificate && run.state.run.status !== "published",
    `${role}: failed observe preview is falsely certified`);
    demand(!fs.existsSync(path.join(dir, "evidence-certificate.json"))
      && !run.events("memory_written").length && !run.events("approval_recorded").length
      && !run.events("completion_admitted").length && !run.events("bounded_correction_requested").length
      && !run.tools.some((tool) => ["request_approval", "file_memory_write"].includes(tool.attributes["gen_ai.tool.name"])),
    `${role}: failed observe preview acquired approval, memory, correction or certificate`);
    demand(result.dashboard === `${final.prefix}/dashboard.html`, `${role}: unsafe/missing observe preview dashboard`);
    safePath(dir, result.dashboard);
  } else {
    demand(final.report.passed && result.status === "completed" && result.certified === true
      && result.attempts === attempts.length && run.state.run.status === "published",
    `${role}: completed run is not independently certified/published`);
    demand(result.dashboard === "dashboard.html" && result.certificate === "evidence-certificate.json",
      `${role}: certified output paths mismatch`);
    const certificate = readJson(dir, result.certificate);
    demand(certificate.trace_id === run.telemetry.trace_id && certificate.event_id === event.event_id,
      `${role}: certificate identity mismatch`);
    same(certificate.verifier, final.report, `${role}: certificate does not contain final nine-check acceptance`);
    same(certificate.source_snapshots, run.ledger.sources, `${role}: certificate source ledger mismatch`);
    for (const [file, key] of [
      ["analysis.json", "analysis_sha256"], ["dashboard.html", "dashboard_sha256"],
      ["generated_analysis.py", "generated_script_sha256"],
    ]) {
      const bytes = fs.readFileSync(safePath(dir, file));
      demand(hash(bytes) === certificate.artifacts?.[key], `${role}: certified artifact hash mismatch: ${file}`);
      demand(bytes.equals(fs.readFileSync(safePath(dir, `${final.prefix}/${file}`))),
        `${role}: certified artifact differs from accepted execution: ${file}`);
    }
    const approvals = run.events("approval_recorded");
    demand(approvals.length === 1 && approvals[0].sequence > final.evaluation.sequence,
      `${role}: approval did not follow acceptance`);
    const approval = approvals[0];
    const tool = run.nativeTool(approval, "request_approval");
    const requests = run.events("approval_requested");
    demand(requests.length === 1 && requests[0].sequence > final.evaluation.sequence
      && requests[0].sequence < approval.sequence && run.nativeTool(requests[0], "request_approval") === tool,
    `${role}: approval request/wait interval is not supported by native execution`);
    const approved = json(tool.attributes["gen_ai.tool.call.result"], "native approval result");
    demand(/^automated-.*-not-human$/.test(approval.kind) && /^automated-/.test(approval.reviewer)
      && certificate.execution?.approval_kind === approval.kind, `${role}: automated approval misrepresented as human`);
    demand(approved.approved === true && approved.receipt === approval.receipt
      && approval.receipt === certificate.approval_receipt && approval.receipt === run.state.approval_receipt,
    `${role}: native approval receipt mismatch`);
    demand(certificate.execution.model === config.model && certificate.execution.deployment === config.deployment,
      `${role}: certificate deployment mismatch`);
    const completion = run.events("completion_admitted");
    demand(completion.length === 1 && completion[0].sequence > approval.sequence, `${role}: completion preceded approval`);
    run.nativeTool(completion[0], "complete_episode");
    run.certificate = certificate;
    run.approvedObservation = approved.memory_record;
  }
  if (role.startsWith("seeded_")) {
    const first = attempts[0];
    demand(first.analysis.event_date === event.announced_at.slice(0, 10)
      && first.report.passed === false
      && first.report.checks.filter((check) => !check.passed).map((check) => check.code).join() === "event_date_alignment",
    `${role}: seeded demonstration lacks an actual isolated date error`);
    if (role === "seeded_strict") {
      const corrections = run.events("bounded_correction_requested");
      demand(config.gate_mode === "strict" && attempts.length === 2 && corrections.length === 1
        && corrections[0].attempt === 1 && corrections[0].remaining === config.max_execution_attempts - 1
        && first.evaluation.sequence < corrections[0].sequence
        && corrections[0].sequence < attempts[1].evaluation.sequence && final.report.passed,
      `${role}: missing fail -> bounded correction -> pass sequence`);
      same(corrections[0].failures, first.report.checks.filter((check) => !check.passed),
        `${role}: correction does not identify the real failed date check`);
    }
  }
  run.attempts = attempts;
}

function validateMemory(run) {
  const { role, config } = run;
  if (!config.memory_enabled) {
    demand(!run.telemetry.events.some((event) => event.event.startsWith("memory_") || event.event === "cross_run_memory_recalled")
      && !run.tools.some((tool) => tool.attributes["gen_ai.tool.name"].startsWith("file_memory_")),
    `${role}: disabled memory still executed`);
    return;
  }
  demand(run.events("memory_index_read").length > 0, `${role}: memory index was not checked`);
  for (const event of run.events("memory_read")) {
    const tool = run.nativeTool(event, "file_memory_read");
    same(json(tool.attributes["gen_ai.tool.call.result"], "native memory read"), event.record,
      `${role}: memory-read event differs from native content`);
    demand(event.scope === config.memory_scope, `${role}: memory read scope mismatch`);
  }
  const written = run.events("memory_written");
  if (!run.result.certified) {
    demand(!written.length, `${role}: uncertified memory write`);
    return;
  }
  demand(written.length === 1, `${role}: missing validated memory observation`);
  const event = written[0];
  const tool = run.nativeTool(event, "file_memory_write");
  const args = parseArguments(tool.attributes["gen_ai.tool.call.arguments"], "native memory write");
  demand(args.file_name === "episode-memory.json" && /^File 'episode-memory\.json' written/.test(tool.attributes["gen_ai.tool.call.result"]),
    `${role}: memory write did not succeed`);
  same(json(args.content, "native memory observation"), event.record, `${role}: native memory-write content mismatch`);
  same(event.record, run.approvedObservation, `${role}: memory observation differs from approved record`);
  demand(event.record.source_trace_id === run.telemetry.trace_id && event.record.kind === "verified-run-observation"
    && event.record.classification === "synthetic-illustrative" && event.scope === config.memory_scope,
  `${role}: invalid memory observation identity/scope`);
  demand(run.events("approval_recorded")[0].sequence < event.sequence
    && event.sequence < run.events("completion_admitted")[0].sequence, `${role}: memory write not bounded by approval/completion`);
  run.writtenObservation = event.record;
}

function validateRun(root, role, id) {
  const base = safePath(root, "demo/live-evidence", "directory");
  const directory = safePath(base, id, "directory");
  const run = {
    role, id, directory,
    telemetry: readJson(directory, "telemetry.json"),
    config: readJson(directory, "harness-config.json"),
    result: readJson(directory, "result.json"),
    state: readJson(directory, "runtime-state.json"),
    session: readJson(directory, "agent-session.json"),
    ledger: readJson(directory, "evidence-ledger.json"),
    policy: readJson(directory, "policy-decision.json"),
  };
  const live = ["warmup", "recall", "all_loaded"].includes(role);
  demand(run.config.model === (live ? "live" : "scripted")
    && run.config.deployment === "gpt-5.6-terra" && run.result.model === run.config.model
    && (!live || run.result.deployment === run.config.deployment),
  `${role}: requested live/seeded deployment mismatch`);
  demand(run.config.skill_mode === (role === "all_loaded" ? "all_loaded" : "progressive")
    && run.config.memory_enabled === (role !== "all_loaded"), `${role}: retained comparison profile mismatch`);
  validateTrace(run);
  demand(run.result.trace_id === run.telemetry.trace_id, `${role}: result trace ID mismatch`);
  validateCalls(run);
  validateSession(run);
  validateSkills(run, root);
  validateSources(run, root);
  validateAcceptance(run, root);
  validateMemory(run);
  return run;
}

function validateLiveEvidence(repoRoot) {
  const root = fs.realpathSync(repoRoot);
  const manifest = readJson(root, "demo/live-evidence/manifest.json");
  demand(manifest.schema_version === 1 && object(manifest.runs), "unsupported retained-evidence manifest");
  same(Object.keys(manifest.runs).sort(), [...ROLES].sort(), "manifest must identify exactly five comparison runs");
  const ids = ROLES.map((role) => manifest.runs[role]);
  demand(ids.every((id) => typeof id === "string" && /^r-[a-f0-9]{16}$/.test(id))
    && new Set(ids).size === ids.length, "unsafe/duplicate manifest run IDs");
  const runs = ROLES.map((role) => validateRun(root, role, manifest.runs[role]));
  demand(new Set(runs.map((run) => run.telemetry.trace_id)).size === runs.length, "cross-run native trace IDs are reused");
  const [warmup, recall] = runs;
  demand(warmup.result.memory_recalled_from === null && !warmup.events("cross_run_memory_recalled").length,
    "warmup unexpectedly recalls a prior run");
  const recalled = recall.events("cross_run_memory_recalled");
  const reads = recall.events("memory_read");
  demand(recalled.length === 1 && reads.length === 1 && recall.config.memory_scope === warmup.config.memory_scope,
    "broken cross-run recall chain/scope");
  same(reads[0].record, warmup.writtenObservation, "recall does not read exactly the first native memory-write observation");
  demand(recalled[0].source_trace_id === warmup.telemetry.trace_id
    && recall.result.memory_recalled_from === warmup.telemetry.trace_id
    && recalled[0].rule === warmup.writtenObservation.event_date_rule
    && reads[0].sequence < recalled[0].sequence
    && recalled[0].sequence < recall.events("plan_recorded")[0]?.sequence,
  "broken memory read -> first-trace recall -> plan chain");
  const plan = recall.nativeTool(recalled[0], "record_plan");
  const planArgs = parseArguments(plan.attributes["gen_ai.tool.call.arguments"], "recalled plan");
  demand(planArgs.recalled_trace_id === warmup.telemetry.trace_id
    && planArgs.recalled_rule === warmup.writtenObservation.event_date_rule,
  "native model plan did not cite the recalled observation");
  demand(instant(warmup.rootSpan.end_time) < instant(recall.rootSpan.start_time), "recall predates the completed warmup");
  return {
    runs: runs.map((run) => ({
      role: run.role, id: run.id, trace_id: run.telemetry.trace_id,
      model: run.config.model, certified: run.result.certified, attempts: run.attempts.length,
      native_spans: run.chats.length + run.agents.length + run.tools.length,
      chat_calls: run.chats.length, tool_calls: run.tools.length,
      initial_input_tokens: run.config.model === "live" ? run.chats[0].attributes["gen_ai.usage.input_tokens"] : null,
      input_tokens: run.config.model === "live" ? run.chats.reduce((n, span) => n + span.attributes["gen_ai.usage.input_tokens"], 0) : null,
      output_tokens: run.config.model === "live" ? run.chats.reduce((n, span) => n + span.attributes["gen_ai.usage.output_tokens"], 0) : null,
      duration_ms: run.rootSpan.duration_ms,
      time_to_approval_request_ms: run.events("approval_requested").length
        ? Number(instant(run.events("approval_requested")[0].at) - instant(run.rootSpan.start_time)) / 1e6 : null,
      approval_wait_ms: run.events("approval_recorded").length
        ? Number(instant(run.events("approval_recorded")[0].at) - instant(run.events("approval_requested")[0].at)) / 1e6 : null,
    })),
    recall_source_trace_id: warmup.telemetry.trace_id,
  };
}

module.exports = { validateLiveEvidence };

if (require.main === module) {
  try {
    console.log(JSON.stringify(validateLiveEvidence(process.argv[2] || path.join(__dirname, "..")), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
