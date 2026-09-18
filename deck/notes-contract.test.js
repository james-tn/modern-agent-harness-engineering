const assert = require("node:assert/strict");
const test = require("node:test");
const { validateDemoNarrative, validatePublicNarrative } = require("./notes-contract");

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
