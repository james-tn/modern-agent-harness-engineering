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

function validateAudienceDocumentation(text, requiredHeadings = []) {
  const logistics = /slide[- ]to[- ]agenda mapping|speaker ownership|presenter runbook|prepared ownership totals|cumulative timing|\bhandoffs?\b|^\s*\*\*Presenters:\*\*/im;
  const schedule = /^\|[^|\r\n]*\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}[^|\r\n]*\|/m;
  if (logistics.test(text) || schedule.test(text)) {
    throw new Error("Audience documentation must not contain presenter logistics.");
  }
  const headings = new Set([...text.matchAll(/^#{1,6}\s+(.+?)\s*$/gm)].map((match) => match[1]));
  for (const heading of requiredHeadings) {
    if (!headings.has(heading)) throw new Error(`Audience documentation missing section: ${heading}`);
  }
}

module.exports = { validateDemoNarrative, validatePublicNarrative, validateAudienceDocumentation };
