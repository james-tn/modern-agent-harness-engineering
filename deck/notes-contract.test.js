const assert = require("node:assert/strict");
const test = require("node:test");
const { validateDemoNarrative, validatePublicNarrative, validateAudienceDocumentation } = require("./notes-contract");

for (const phrase of ["only demonstrates preselection", "not observed behavior", "is an extension"]) {
  test(`rejects an unscoped under-claim: ${phrase}`, () => {
    assert.throws(() => validateDemoNarrative(`The walkthrough ${phrase}.`), /Unscoped stale/);
    assert.throws(
      () => validateDemoNarrative(`A legacy video is available. The live walkthrough ${phrase}.`),
      /Unscoped stale/,
    );
  });
  test(`allows an explicitly legacy-scoped limitation: ${phrase}`, () => {
    assert.doesNotThrow(() => validateDemoNarrative(`For the legacy recording, this ${phrase}.`));
  });
}

test("keeps the selection-versus-loading distinction without understating the live demo", () => {
  validateDemoNarrative(
    "A selected list is not evidence of loading. James will show a model-issued load_skill call. "
    + "The legacy prerecorded fixture only shows preselection.",
  );
});

test("public presentation excludes private planning attribution", () => {
  for (const phrase of ["Internal planning sync", "same-title planning chat", "sync-selected domain"]) {
    assert.throws(() => validatePublicNarrative(phrase), /Private planning/);
  }
});

test("repository citations use the public destination rather than a private source", () => {
  assert.throws(
    () => validatePublicNarrative("https://github.com/private-owner/modern-agent-harness-engineering/tree/main"),
    /public james-tn/,
  );
  assert.doesNotThrow(() => validatePublicNarrative(
    "https://github.com/james-tn/modern-agent-harness-engineering/tree/main "
    + "https://github.com/microsoft/agent-framework",
  ));
});

for (const text of [
  "## Slide-to-agenda mapping",
  "## Speaker ownership",
  "Read the presenter runbook.",
  "Prepared ownership totals: 11 minutes.",
  "| Slide | Cumulative timing |",
  "The next handoff names the speaker.",
  "**Presenters:** Example Person",
  "| 0:00–6:00 | Welcome | Example Person |",
]) {
  test(`audience docs reject logistics: ${text}`, () => {
    assert.throws(() => validateAudienceDocumentation(text), /presenter logistics/);
  });
}

test("audience docs require useful content rather than an empty stripped README", () => {
  assert.throws(
    () => validateAudienceDocumentation("# Demo", ["Strict acceptance gates"]),
    /missing section/,
  );
  assert.doesNotThrow(() => validateAudienceDocumentation(
    "# Demo\n\n## Strict acceptance gates\n\nThree execution attempts; no unlimited retries.\n"
    + "## Recall and retain observations\n\nMemory does not override policy.",
    ["Strict acceptance gates", "Recall and retain observations"],
  ));
});
