"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { validateLiveEvidence } = require("./validate-live");

const ROOT = path.join(__dirname, "..");
// The inputs are real retained MAF traces, never manufactured model/tool spans.
const RETAINED_RUNS = {
  warmup: "r-98af89a2478e80c2",
  recall: "r-179fbefb3be66bde",
  all_loaded: "r-34c80beda5b222d1",
  seeded_observe: "r-5a5e7d319bfbd70e",
  seeded_strict: "r-4a832f54f04fe8ae",
};

function fixture(context) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "retained-native-evidence-test-"));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const relative of [
    path.join("demo", "sample-input"),
    path.join("demo", "agent", "skills"),
    ...Object.values(RETAINED_RUNS).map((id) => path.join("demo", "live-evidence", id)),
  ]) {
    fs.cpSync(path.join(ROOT, relative), path.join(root, relative), { recursive: true });
  }
  fs.writeFileSync(path.join(root, "demo", "live-evidence", "manifest.json"),
    JSON.stringify({ schema_version: 1, runs: RETAINED_RUNS }));
  return root;
}

function file(root, role, name) {
  return path.join(root, "demo", "live-evidence", RETAINED_RUNS[role], name);
}

function edit(filename, mutation) {
  const data = JSON.parse(fs.readFileSync(filename, "utf8"));
  mutation(data);
  fs.writeFileSync(filename, JSON.stringify(data));
}

function telemetry(root, role, mutation) {
  edit(file(root, role, "telemetry.json"), mutation);
}

function tool(trace, name) {
  return trace.spans.find((span) => span.attributes["gen_ai.tool.name"] === name);
}

function eventMutation(root, role, name, mutation) {
  telemetry(root, role, (trace) => {
    const event = trace.events.find((item) => item.event === name);
    mutation(event, trace);
    const native = trace.spans.flatMap((span) => span.events).find((item) =>
      item.attributes?.["harness.event.id"] === event.id);
    const details = JSON.parse(native.attributes["harness.event.details"]);
    mutation(details, trace);
    native.attributes["harness.event.details"] = JSON.stringify(details);
  });
  edit(file(root, role, "runtime-state.json"), (state) => mutation(state.events.find((event) => event.event === name)));
}

function removeEvent(root, role, name) {
  telemetry(root, role, (trace) => {
    const removed = new Set(trace.events.filter((event) => event.event === name).map((event) => event.id));
    trace.events = trace.events.filter((event) => !removed.has(event.id));
    for (const span of trace.spans) {
      span.events = span.events.filter((event) => !removed.has(event.attributes?.["harness.event.id"]));
    }
    trace.events.forEach((event, index) => {
      const original = trace.spans.flatMap((span) => span.events).find((item) =>
        item.attributes?.["harness.event.id"] === event.id);
      event.sequence = index + 1;
      event.id = `${trace.trace_id}:${String(index + 1).padStart(6, "0")}`;
      original.attributes["harness.event.sequence"] = event.sequence;
      original.attributes["harness.event.id"] = event.id;
    });
  });
  edit(file(root, role, "runtime-state.json"), (state) => {
    state.events = state.events.filter((event) => event.event !== name);
  });
}

function negative(name, mutation, expected) {
  test(name, (context) => {
    const root = fixture(context);
    mutation(root);
    assert.throws(() => validateLiveEvidence(root), expected);
  });
}

test("real retained native evidence validates offline with nonduplicated chat usage totals", (context) => {
  const root = fixture(context);
  const summary = validateLiveEvidence(root);
  assert.equal(summary.runs.length, 5);
  assert.equal(summary.runs.filter((run) => run.certified).length, 4);
  assert.equal(summary.recall_source_trace_id, "4033a15ace7384723a22f98eda1b44de");
  for (const run of summary.runs) {
    assert.ok(run.chat_calls > 0 && run.tool_calls > 0 && run.duration_ms > 0);
    if (run.model === "live") {
      const native = JSON.parse(fs.readFileSync(file(root, run.role, "telemetry.json")));
      const expected = native.spans.filter((span) => span.attributes["gen_ai.operation.name"] === "chat")
        .reduce((total, span) => total + span.attributes["gen_ai.usage.input_tokens"], 0);
      assert.equal(run.input_tokens, expected);
      assert.equal(run.initial_input_tokens,
        native.spans.find((span) => span.attributes["gen_ai.operation.name"] === "chat").attributes["gen_ai.usage.input_tokens"]);
      assert.ok(run.output_tokens > 0);
    } else {
      assert.equal(run.input_tokens, null);
      assert.equal(run.output_tokens, null);
      assert.equal(run.initial_input_tokens, null);
    }
    if (run.certified) {
      assert.ok(run.time_to_approval_request_ms > 0 && run.approval_wait_ms >= 0);
      assert.ok(run.time_to_approval_request_ms + run.approval_wait_ms <= run.duration_ms);
    } else {
      assert.equal(run.time_to_approval_request_ms, null);
      assert.equal(run.approval_wait_ms, null);
    }
  }
});

negative("rejects unsafe manifest run paths", (root) => {
  edit(path.join(root, "demo", "live-evidence", "manifest.json"), (manifest) => {
    manifest.runs.warmup = "../r-98af89a2478e80c2";
  });
}, /unsafe\/duplicate manifest run IDs/);

negative("rejects missing required retained evidence", (root) => {
  fs.unlinkSync(file(root, "warmup", "agent-session.json"));
}, /missing required file: agent-session/);

negative("rejects a native-looking span without native origin", (root) => {
  telemetry(root, "warmup", (trace) => { tool(trace, "load_skill").origin = "application"; });
}, /native MAF origin\/scope/);

negative("rejects invented native instrumentation scope/version", (root) => {
  telemetry(root, "warmup", (trace) => { tool(trace, "load_skill").instrumentation_scope.version = "custom-writer"; });
}, /native MAF origin\/scope/);

negative("rejects missing native chat instrumentation", (root) => {
  telemetry(root, "warmup", (trace) => {
    trace.spans = trace.spans.filter((span) => span.attributes["gen_ai.operation.name"] !== "chat");
  });
}, /agent\/chat\/tool span layer is missing/);

negative("rejects orphaned native parent IDs", (root) => {
  telemetry(root, "warmup", (trace) => { tool(trace, "load_skill").parent_span_id = "1111111111111111"; });
}, /orphaned native span parent/);

negative("rejects cross-run trace leakage", (root) => {
  telemetry(root, "warmup", (trace) => { tool(trace, "load_skill").trace_id = "22222222222222222222222222222222"; });
}, /cross-trace span leakage/);

negative("rejects invented native tool call IDs", (root) => {
  telemetry(root, "warmup", (trace) => { tool(trace, "load_skill").attributes["gen_ai.tool.call.id"] = "call_never_issued"; });
}, /no unique model-issued call ID/);

negative("rejects missing assistant-issued calls, even when the native tool span exists", (root) => {
  telemetry(root, "warmup", (trace) => {
    const id = tool(trace, "load_skill").attributes["gen_ai.tool.call.id"];
    for (const span of trace.spans.filter((item) => item.attributes["gen_ai.operation.name"] === "chat")) {
      const messages = JSON.parse(span.attributes["gen_ai.output.messages"]);
      for (const message of messages) message.parts = message.parts.filter((part) => part.id !== id);
      span.attributes["gen_ai.output.messages"] = JSON.stringify(messages);
    }
  });
}, /no unique model-issued call ID/);

negative("rejects tool arguments not issued by the model", (root) => {
  telemetry(root, "warmup", (trace) => {
    tool(trace, "execute_analysis").attributes["gen_ai.tool.call.arguments"] = '{"event_date":"1900-01-01"}';
  });
}, /arguments differ from model-issued call/);

negative("rejects missing native tool results", (root) => {
  telemetry(root, "warmup", (trace) => { delete tool(trace, "load_skill").attributes["gen_ai.tool.call.result"]; });
}, /native tool result is missing/);

negative("rejects fabricated application events without an OTel source", (root) => {
  telemetry(root, "warmup", (trace) => {
    const event = trace.events.find((item) => item.event === "skill_loaded");
    for (const span of trace.spans) {
      span.events = span.events.filter((item) => item.attributes?.["harness.event.id"] !== event.id);
    }
  });
}, /application event has no OTel source/);

negative("rejects unsupported successful skill-loading claims", (root) => {
  eventMutation(root, "warmup", "skill_loaded", (event) => { event.skill = "invented-skill"; });
}, /selection has no successful load|unsupported loaded skill/);

negative("rejects skill use with no successful loading", (root) => {
  removeEvent(root, "warmup", "skill_loaded");
}, /missing progressive native skill loading/);

negative("rejects skill result/hash mismatches", (root) => {
  telemetry(root, "warmup", (trace) => {
    tool(trace, "load_skill").attributes["gen_ai.tool.call.result"] += "\nInvented retained content.";
  });
}, /native loaded skill result\/hash mismatch/);

negative("rejects all-loaded claims without actual preloaded model content", (root) => {
  telemetry(root, "all_loaded", (trace) => {
    trace.spans.find((span) => span.attributes["gen_ai.operation.name"] === "chat")
      .attributes["gen_ai.system_instructions"] = '[{"type":"text","content":"Metadata names alone are not loaded skills."}]';
  });
}, /preload not supported by actual native model input/);

negative("rejects different AgentSession identity between turns and saved history", (root) => {
  edit(file(root, "warmup", "agent-session.json"), (session) => { session.session_id = "different-session"; });
}, /do not share the saved AgentSession/);

negative("rejects a broken first-run observation recalled by the second", (root) => {
  eventMutation(root, "recall", "memory_read", (event) => { event.record.policy_version = "invented-version"; });
  telemetry(root, "recall", (trace) => {
    const native = tool(trace, "file_memory_read");
    const record = JSON.parse(native.attributes["gen_ai.tool.call.result"]);
    record.policy_version = "invented-version";
    native.attributes["gen_ai.tool.call.result"] = JSON.stringify(record);
  });
}, /does not read exactly the first native memory-write observation/);

negative("rejects a recall event pointing to a different native trace", (root) => {
  eventMutation(root, "recall", "cross_run_memory_recalled", (event) => {
    event.source_trace_id = "33333333333333333333333333333333";
  });
}, /broken memory read -> first-trace recall -> plan chain/);

negative("rejects changed source snapshots", (root) => {
  fs.appendFileSync(path.join(root, "demo", "sample-input", "market-prices.json"), "\n");
}, /source content hash mismatch/);

negative("rejects native retrieval content inconsistent with hashed source inputs", (root) => {
  telemetry(root, "warmup", (trace) => {
    const native = tool(trace, "public_source_search");
    const result = JSON.parse(native.attributes["gen_ai.tool.call.result"]);
    result.market.rows[0].ACX = 9999;
    native.attributes["gen_ai.tool.call.result"] = JSON.stringify(result);
  });
}, /native public retrieval differs from hashed source/);

negative("rejects private portfolio fields inserted into native redacted retrieval", (root) => {
  telemetry(root, "warmup", (trace) => {
    const native = trace.spans.find((span) => span.attributes["gen_ai.tool.name"] === "internal_api_lookup"
      && JSON.parse(span.attributes["gen_ai.tool.call.arguments"]).resource === "portfolio");
    const result = JSON.parse(native.attributes["gen_ai.tool.call.result"]);
    result.data.shares = 125000;
    native.attributes["gen_ai.tool.call.result"] = JSON.stringify(result);
  });
}, /native internal retrieval differs from hashed\/redacted source/);

negative("rejects changed certified artifact bytes", (root) => {
  fs.appendFileSync(file(root, "warmup", "dashboard.html"), "\n");
}, /certified artifact hash mismatch/);

negative("rejects missing independent acceptance checks", (root) => {
  edit(file(root, "warmup", "verification-1.json"), (report) => { report.checks.pop(); });
}, /nine distinct verifier checks/);

negative("rejects automated approval presented as human", (root) => {
  eventMutation(root, "warmup", "approval_recorded", (event) => { event.kind = "human-review"; });
}, /automated approval misrepresented as human/);

negative("rejects missing native-backed approval request timing", (root) => {
  removeEvent(root, "warmup", "approval_requested");
}, /approval request\/wait interval is not supported/);

negative("rejects observe-only false certification", (root) => {
  edit(file(root, "seeded_observe", "result.json"), (result) => {
    result.certified = true;
    result.status = "completed";
  });
}, /failed observe preview is falsely certified/);

negative("rejects an evidence certificate added to a failed observe preview", (root) => {
  fs.copyFileSync(file(root, "warmup", "evidence-certificate.json"), file(root, "seeded_observe", "evidence-certificate.json"));
}, /failed observe preview acquired/);

negative("rejects a seeded strict run without bounded correction evidence", (root) => {
  removeEvent(root, "seeded_strict", "bounded_correction_requested");
}, /missing fail -> bounded correction -> pass sequence/);

negative("rejects actual credential-bearing telemetry headers", (root) => {
  telemetry(root, "warmup", (trace) => {
    trace.spans[0].attributes["http.request.header.authorization"] = "Bearer synthetic-credential-for-negative-test";
  });
}, /credential\/header field/);

negative("rejects nested credentials inside native JSON results", (root) => {
  telemetry(root, "warmup", (trace) => {
    tool(trace, "request_approval").attributes["gen_ai.tool.call.result"] = '{"access_token":"test-credential-value"}';
  });
}, /credential\/header field/);

negative("rejects private meeting links", (root) => {
  telemetry(root, "warmup", (trace) => {
    trace.spans[0].attributes["test.reference"] = "https://teams.microsoft.com/l/meetup-join/private-negative-test";
  });
}, /private meeting URL/);

test("harmless token/credential instructions and JSON-schema descriptions are not secrets", (context) => {
  const root = fixture(context);
  telemetry(root, "warmup", (trace) => {
    trace.spans[0].attributes["test.description"] = "Track token usage; never log API keys, credentials or headers.";
    trace.spans[0].attributes["test.schema"] = JSON.stringify({
      properties: { access_token: { type: "string", description: "A token property description, not an actual credential." } },
    });
  });
  assert.equal(validateLiveEvidence(root).runs.length, 5);
});
