function validateDemoNarrative(notes) {
  const stale = /only demonstrates preselection|not observed behavior|is an extension/i;
  for (const sentence of notes.split(/(?<=[.!?])\s+|\n+/u)) {
    if (stale.test(sentence) && !/\blegacy\b/i.test(sentence)) {
      throw new Error(`Unscoped stale demo limitation: ${sentence.trim()}`);
    }
  }
}

function validatePublicNarrative(text) {
  if (/internal planning sync|same-title planning chat|sync-selected/i.test(text)) {
    throw new Error("Private planning attribution must not appear in the public presentation.");
  }
  for (const [, owner] of text.matchAll(/https:\/\/github\.com\/([^/\s]+)\/modern-agent-harness-engineering\b/gi)) {
    if (owner.toLowerCase() !== "james-tn") {
      throw new Error("Repository citations must point to the public james-tn snapshot.");
    }
  }
}

module.exports = { validateDemoNarrative, validatePublicNarrative };
