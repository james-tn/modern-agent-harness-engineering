const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { execFileSync } = require("child_process");
const { validateLiveEvidence } = require("./validate-live");
const { validateDemoNarrative, validatePublicNarrative } = require("./notes-contract");

const root = path.join(__dirname, "..");
const pptx = process.env.DECK_OUT
  ? path.resolve(process.env.DECK_OUT)
  : path.join(root, "Modern-Agent-Harness-Engineering.pptx");
const narratedVideo = path.join(root, "demo", "media", "equity-event-harness-demo.mp4");
const narratedCover = path.join(root, "demo", "media", "equity-event-harness-demo-cover.png");
const narratedMetadata = path.join(root, "demo", "media", "equity-event-harness-demo.metadata.json");
const narratedStoryboard = path.join(root, "demo", "recording", "storyboard.json");
const requirementsPath = path.join(root, "demo", "agent", "requirements.txt");

function fail(message) {
  console.error(`VALIDATION FAILED: ${message}`);
  process.exit(1);
}

if (!fs.existsSync(pptx) || fs.statSync(pptx).size < 100000) fail("PPTX is missing or unexpectedly small.");
for (const artifact of [narratedVideo, narratedCover, narratedMetadata, narratedStoryboard, requirementsPath]) {
  if (!fs.existsSync(artifact)) fail(`Missing retained demo artifact: ${path.relative(root, artifact)}`);
}

const narration = JSON.parse(fs.readFileSync(narratedMetadata, "utf8"));
const requirements = fs.readFileSync(requirementsPath, "utf8");
if (!/^agent-framework-core==1\.18\.0\s*$/m.test(requirements) || /^agent-framework(?:\[|\s|[<>=!~@;]|$)/m.test(requirements)) {
  fail("Demo must pin Agent Framework core 1.18.0 without the unused umbrella package.");
}
for (const pin of ["agent-framework-openai==1.14.3", "azure-identity==1.25.3", "opentelemetry-sdk==1.44.0"]) {
  if (!requirements.split(/\r?\n/).includes(pin)) fail(`Missing live runtime pin: ${pin}`);
}
try {
  validateLiveEvidence(root);
} catch (error) {
  fail(`Retained live evidence: ${error.message}`);
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

let narrationEndpoint;
try {
  narrationEndpoint = new URL(narration.endpoint);
} catch {
  fail("Narration endpoint provenance is missing or invalid.");
}
const trustedNarrationHost = narrationEndpoint.hostname.endsWith(".cognitiveservices.azure.com") || narrationEndpoint.hostname.endsWith(".services.ai.azure.com");
if (
  narration.provider !== "Microsoft Foundry"
  || narration.model !== "gpt-4o-mini-tts"
  || narration.deployment !== "gpt-4o-mini-tts"
  || narration.voice !== "onyx"
  || narrationEndpoint.protocol !== "https:"
  || !trustedNarrationHost
  || narrationEndpoint.pathname.replace(/\/$/, "") !== "/openai/v1/audio/speech"
) fail("Narration model provenance mismatch.");
if (sha256(narratedVideo) !== narration.video_sha256 || sha256(narratedCover) !== narration.cover_sha256 || sha256(narratedStoryboard) !== narration.storyboard_sha256) fail("Narrated demo hash mismatch.");
const metadataDuration = Number(narration.duration_seconds);
if (!Number.isFinite(metadataDuration) || metadataDuration < 160 || metadataDuration > 175 || narration.segments?.length !== 5) fail("Narrated demo duration or segment count mismatch.");
let mediaProbe;
try {
  mediaProbe = JSON.parse(execFileSync("ffprobe", [
    "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration,size",
    "-of", "json", narratedVideo,
  ], { encoding: "utf8" }));
} catch (error) {
  fail(`Unable to inspect narrated demo: ${error.message}`);
}
const videoStream = mediaProbe.streams?.find((stream) => stream.codec_type === "video");
const audioStream = mediaProbe.streams?.find((stream) => stream.codec_type === "audio");
if (videoStream?.codec_name !== "h264" || videoStream.width !== 1920 || videoStream.height !== 1080 || audioStream?.codec_name !== "aac") fail("Narrated demo must contain 1920x1080 H.264 video and AAC audio.");
const probedDuration = Number(mediaProbe.format?.duration);
if (!Number.isFinite(probedDuration) || Math.abs(probedDuration - metadataDuration) > 0.05) fail("Probed narrated-demo duration does not match metadata.");
if (!narration.segments.every((segment) => /^[a-f0-9]{64}$/.test(segment.request_fingerprint || ""))) fail("Narration request fingerprints are missing.");

const timings = [
  "0:00-0:30", "0:30-1:00", "1:00-6:00", "6:00-10:00",
  "10:00-14:00", "14:00-18:00", "18:00-22:00", "22:00-25:00",
  "25:00-26:00", "26:00-29:00", "29:00-30:00", "30:00-45:00",
  "45:00 / untimed references",
];
const james = "James Nguyen";
const alexandre = "Alexandre Delarue";
const kunwarpreet = "Kunwarpreet Behar";
const allSpeakers = `${james}, ${alexandre} and ${kunwarpreet}`;
const speakers = [
  james, james, james, alexandre, alexandre, kunwarpreet, kunwarpreet,
  alexandre, james, james, james, allSpeakers, allSpeakers,
];
const segments = [
  ...Array(8).fill("prepared"), ...Array(3).fill("demo"), "discussion", "references",
];
const ps = `
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead('${pptx.replace(/'/g, "''")}')
function Read-Part($name) {
  $entry = $zip.GetEntry($name)
  if ($null -eq $entry) { throw "Missing OOXML part: $name" }
  $reader = [System.IO.StreamReader]::new($entry.Open())
  try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Plain-Text($xml) {
  return (($xml.SelectNodes('.//*[local-name()="t"]') | ForEach-Object { $_.InnerText }) -join [char]10)
}
try {
  $xmlCount = 0
  foreach ($entry in $zip.Entries) {
    if ($entry.FullName -match '[.](xml|rels)$') {
      [xml](Read-Part $entry.FullName) | Out-Null
      $xmlCount++
    }
  }
  $slideCount = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/slides/slide[0-9]+[.]xml$' }).Count
  $noteCount = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/notesSlides/notesSlide[0-9]+[.]xml$' }).Count
  $slides = @(for ($i = 1; $i -le $slideCount; $i++) {
    [xml]$xml = Read-Part "ppt/slides/slide$i.xml"
    [xml]$note = Read-Part "ppt/notesSlides/notesSlide$i.xml"
    [xml]$slideRels = Read-Part "ppt/slides/_rels/slide$i.xml.rels"
    $noteLinks = @($slideRels.Relationships.Relationship | Where-Object { $_.Type -match '/notesSlide$' })
    $notesLinked = $false
    if ($noteLinks.Count -eq 1 -and $noteLinks[0].TargetMode -ne 'External') {
      $noteTarget = [uri]::new([uri]"https://pptx.invalid/ppt/slides/slide$i.xml", [string]$noteLinks[0].Target).AbsolutePath.TrimStart('/')
      $notesLinked = $noteTarget -eq "ppt/notesSlides/notesSlide$i.xml"
    }
    $footers = @($xml.SelectNodes('//*[local-name()="sp"]') | Where-Object { (Plain-Text $_) -match '^SOURCE:' })
    $footerSizes = @($footers | ForEach-Object { $_.SelectNodes('.//*[local-name()="rPr"]/@sz') } | ForEach-Object { [int]$_.Value / 100 })
    $noteText = Plain-Text $note
    $speaker = [regex]::Match($noteText, 'PRESENTER\\s+([^\\r\\n]+)').Groups[1].Value.Trim()
    $presenters = @($xml.SelectNodes('//*[local-name()="sp"]') | Where-Object {
      $offset = $_.SelectSingleNode('./*[local-name()="spPr"]/*[local-name()="xfrm"]/*[local-name()="off"]')
      (Plain-Text $_) -eq $speaker -and $null -ne $offset -and [long]$offset.y -ge 6600000
    })
    $presenterSizes = @($presenters | ForEach-Object { $_.SelectNodes('.//*[local-name()="rPr"]/@sz') } | ForEach-Object { [int]$_.Value / 100 })
    [pscustomobject]@{
      number = $i; text = Plain-Text $xml; notes = $noteText
      sourceCount = $footers.Count; sourceSizes = $footerSizes; notesLinked = $notesLinked
      presenterCount = $presenters.Count; presenterSizes = $presenterSizes
    }
  })
  $videos = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/media/.+[.]mp4$' })
  $hash = ''
  if ($videos.Count -eq 1) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $stream = $videos[0].Open()
    try { $hash = ([System.BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
  }
  [xml]$rels = Read-Part 'ppt/slides/_rels/slide10.xml.rels'
  $videoRels = @($rels.Relationships.Relationship | Where-Object { $_.Type -match '/video$' })
  $mediaLinked = $false
  if ($videoRels.Count -eq 1 -and $videoRels[0].TargetMode -ne 'External') {
    $target = [uri]::new([uri]'https://pptx.invalid/ppt/slides/slide10.xml', [string]$videoRels[0].Target).AbsolutePath.TrimStart('/')
    $mediaLinked = $videos.Count -eq 1 -and $target -eq $videos[0].FullName
  }
  [xml]$videoSlide = Read-Part 'ppt/slides/slide10.xml'
  $videoReferences = @($videoSlide.SelectNodes('//*[local-name()="videoFile"]'))
  $referenceBound = $false
  if ($videoReferences.Count -eq 1 -and $videoRels.Count -eq 1) {
    $referenceBound = $videoReferences[0].GetAttribute('link', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships') -eq $videoRels[0].Id
  }
  [pscustomobject]@{
    slides = $slides; notes = $noteCount; xmlParts = $xmlCount
    videoCount = $videos.Count; videoHash = $hash
    mediaLinked = $mediaLinked; referenceBound = $referenceBound
  } | ConvertTo-Json -Depth 8 -Compress
} finally { $zip.Dispose() }
`;
let deck;
try {
  deck = JSON.parse(execFileSync("powershell", ["-NoProfile", "-Command", ps], { encoding: "utf8", maxBuffer: 4 * 1024 * 1024 }));
} catch (error) {
  fail(error.stdout || error.message);
}
if (deck.slides?.length !== 13 || deck.notes !== 13) fail("Expected 11 prepared slides, one discussion slide and one references slide, each with notes.");
let elapsed = 0;
let preparedSeconds = 0;
let demoSeconds = 0;
let discussionSeconds = 0;
const speakerSeconds = new Map();
const seconds = (time) => time.split(":").reduce((minutes, part) => minutes * 60 + Number(part), 0);
for (const [i, page] of deck.slides.entries()) {
  try {
    validateDemoNarrative(page.notes);
  } catch (error) {
    fail(`Slide ${i + 1}: ${error.message}`);
  }
  const noteTiming = page.notes.match(/CUMULATIVE TIMING\s+([^\r\n]+)/)?.[1]?.trim();
  const speaker = page.notes.match(/PRESENTER\s+([^\r\n]+)/)?.[1]?.trim();
  const segment = page.notes.match(/SESSION SEGMENT\s+([^\r\n]+)/)?.[1]?.trim();
  if (noteTiming !== timings[i]) fail(`Slide ${i + 1} timing mismatch: ${noteTiming}`);
  if (speaker !== speakers[i]) fail(`Slide ${i + 1} presenter mismatch: ${speaker}`);
  if (segment !== segments[i]) fail(`Slide ${i + 1} segment mismatch: ${segment}`);
  if (page.presenterCount !== 1 || !page.presenterSizes.length || page.presenterSizes.some((size) => size < 10.5)) fail(`Slide ${i + 1} needs a visible presenter label (>=10.5 pt).`);
  if (!page.notesLinked) fail(`Slide ${i + 1} notes relationship mismatch.`);
  if (i < 12) {
    if (!page.text.includes(noteTiming)) fail(`Slide ${i + 1} visible timing disagrees with its notes.`);
    const [start, end] = noteTiming.split("-").map(seconds);
    if (start !== elapsed || end <= start) fail(`Timing gap or overlap at slide ${i + 1}.`);
    elapsed = end;
    if (segment === "prepared" || segment === "demo") {
      preparedSeconds += end - start;
      speakerSeconds.set(speaker, (speakerSeconds.get(speaker) || 0) + end - start);
      if (end > 1800) fail("Prepared content must stop by 30:00.");
    }
    if (segment === "demo") demoSeconds += end - start;
    if (segment === "discussion") discussionSeconds += end - start;
  }
  if (page.sourceCount !== 1 || !page.sourceSizes.length || page.sourceSizes.some((size) => size < 10.5)) fail(`Slide ${i + 1} needs one legible SOURCE footer (>=10.5 pt).`);
  for (const heading of ["SLIDE EXPLANATION", "PRESENTER TALK TRACK", "HANDOFF", "CITATIONS"]) {
    if (!page.notes.includes(heading)) fail(`Slide ${i + 1} notes missing ${heading}.`);
  }
  const handoff = page.notes.split("HANDOFF\n")[1]?.split("\n\nCITATIONS")[0] || "";
  const nextSpeaker = speakers[Math.min(i + 1, speakers.length - 1)];
  if (!handoff.includes(nextSpeaker)) fail(`Slide ${i + 1} handoff must name the next speaker: ${nextSpeaker}`);
  const citations = page.notes.split("CITATIONS\n")[1] || "";
  if (!/https:\/\/\S+/.test(citations)) fail(`Slide ${i + 1} notes need full source URLs.`);
  for (const [, marker] of page.text.matchAll(/\[([A-Z]\d*)\]/g)) {
    if (!citations.includes(`[${marker}]`)) fail(`Slide ${i + 1} visible source [${marker}] has no note citation.`);
  }
  if (i < 8 && /Microsoft Agent Framework|\bMAF\b|gpt-4o-mini-tts/i.test(page.text + page.notes)) fail(`Conceptual slide ${i + 1} is not framework-neutral.`);
  if (i < 11 && /HarnessFix|ClawVM|Proof-Carrying|[+-]5[.]91|>85%|~55K/i.test(page.text)) fail(`Slide ${i + 1} reintroduces excluded research or financial/statistical teaching content.`);
}
if (elapsed !== 2700 || preparedSeconds !== 1800 || demoSeconds !== 300 || discussionSeconds !== 900) fail("Expected 30:00 prepared including a 5:00 demo, then a proposed 15:00 discussion.");
if (speakerSeconds.get(james) !== 660 || speakerSeconds.get(alexandre) !== 660 || speakerSeconds.get(kunwarpreet) !== 480) fail("Prepared speaker allocation must be James 11, Alexandre 11, Kunwarpreet 8 minutes.");
const readme = fs.readFileSync(path.join(root, "README.md"), "utf8");
const runbook = fs.readFileSync(path.join(root, "demo", "README.md"), "utf8");
const agendaRows = [...readme.matchAll(/^\|\s*(\d+)\s*\|([^\r\n]+)$/gm)];
if (agendaRows.length !== 13) fail("README must map all 13 slides.");
agendaRows.forEach((row, i) => {
  const expected = i === 12 ? "45:00" : timings[i];
  const cells = row[2].split("|").map((cell) => cell.trim());
  if (Number(row[1]) !== i + 1 || !cells.includes(expected)) fail(`README slide ${i + 1} timing mismatch.`);
  if (!cells.includes(speakers[i])) fail(`README slide ${i + 1} speaker mismatch.`);
});
for (const [name, doc] of [["README", readme], ["presenter runbook", runbook]]) {
  for (const token of ["Public snapshot", "30+15", "proposed", james, alexandre, kunwarpreet]) {
    if (!doc.replace(/\r?\n/g, " ").includes(token)) fail(`${name} missing public scope/timing/speaker detail: ${token}`);
  }
}
const ownership = [
  ["0:00–6:00", james], ["6:00–14:00", alexandre], ["14:00–22:00", kunwarpreet],
  ["22:00–25:00", alexandre], ["25:00–30:00", james], ["30:00–45:00", allSpeakers],
];
for (const doc of [readme, runbook]) {
  for (const [range, speaker] of ownership) {
    if (!doc.split(/\r?\n/).some((row) => row.includes(range) && row.includes(speaker))) fail(`Speaker ownership map missing ${range}: ${speaker}`);
  }
}
const allDeckText = deck.slides.map((page) => page.text + "\n" + page.notes).join("\n");
try {
  validatePublicNarrative(allDeckText + readme + runbook);
} catch (error) {
  fail(error.message);
}
if (/https?:\/\/[^\s]*(?:sharepoint\.com|teams\.microsoft\.com|teams\.live\.com)/i.test(allDeckText + readme + runbook)) fail("Private meeting URLs must not be copied into the deck or runbooks.");
function expectSlide(number, visible, noteTokens = []) {
  const page = deck.slides[number - 1];
  for (const token of visible) {
    if (!page.text.includes(token)) fail(`Slide ${number} missing visible claim/control: ${token}`);
  }
  for (const token of noteTokens) {
    if (!page.notes.includes(token)) fail(`Slide ${number} missing supporting detail: ${token}`);
  }
}
expectSlide(1, ["Modern Concepts and Techniques", james, alexandre, kunwarpreet]);
expectSlide(2, [james, alexandre, kunwarpreet, "0–6", "6–14", "14–22", "22–25", "25–30", "30–45", "proposed"], ["not a fixed 45-minute lecture"]);
expectSlide(3, ["PROMPT", "CONTEXT", "HARNESS", "Dynamic context"], ["Do not call context engineering static"]);
expectSlide(4, ["INSTRUCTIONS + CONTEXT", "TOOLS + SKILLS", "MEMORY / STATE", "EXECUTION ENVIRONMENT", "TELEMETRY"], ["illustrative design decomposition"]);
expectSlide(5, ["GOAL", "ACT", "OBSERVE", "STOP / ESCALATE", "Budget limit", "No-progress guard", "Human boundary"], ["doom loops"]);
expectSlide(6, ["ALL-LOADED", "PROGRESSIVE", "DISCOVER", "SELECT", "LOAD", "Mandatory policy"], ["discovered, selected, loaded and invoked", "model-issued load_skill", "legacy prerecorded"]);
expectSlide(7, ["Goal + constraints", "Compact bulky results", "DURABLE MEMORY / STATE"], ["Goal drift"]);
expectSlide(8, ["CHECK", "APPROVE", "bounded correction", "budget exhausted"], ["Passing tests does not authorize"]);
expectSlide(9, ["1.18.0", "available illustration", "synthetic data", "PROGRESSIVE TOOLING", "CONTEXT HYGIENE", "ACCEPTANCE GATES", "Mandatory policy stays on"], ["agent-framework-core==1.18.0", "create_harness_agent", "SkillsProvider.load_skill", "FileMemoryProvider", "not an OS sandbox", "Compaction is off", "experimental"]);
expectSlide(10, ["legacy scripted fallback", "Real tool spans", "On-demand skills", "Memory + gates", "Video predates"], ["164.45-second", "scripted reviewer approval", "not a recording of core 1.18", "not investment advice", "saved live evidence"]);
expectSlide(11, ["LIVE MODEL EVIDENCE", "SEEDED OFFLINE NEAR-MISS", "cross_run_memory_recalled", "passed: false", "bounded_correction_requested"], ["source_trace_id", "MAF", "Scripted / offline", "Close the prepared material at 30:00", "Do not expect the live model to fail"]);
expectSlide(12, ["proposed 30:00–45:00", "TOOL OVERLOAD", "CONTEXT DRIFT", "ACCEPTANCE FAILURE"], ["discussion, not prepared lecture", "proposed allocation"]);
expectSlide(13, ["PUBLIC GUIDANCE", "ACTUAL DEMO EVIDENCE", "DELIVERY BOUNDARY", "Synthetic illustration only", "proposed allocation"], ["python-1.18.0", "https://github.com/james-tn/modern-agent-harness-engineering"]);
if (deck.videoCount !== 1 || deck.videoHash !== narration.video_sha256 || !deck.mediaLinked || !deck.referenceBound) fail("Slide 10 must embed and reference the exact narrated MP4.");

console.log("slides=13\nnotes=13\nprepared_content=30:00\ndemo=5:00\ndiscussion=15:00_proposed\nreadme_timing=matched");
console.log("prepared_speakers=James_11m_Alexandre_11m_Kunwarpreet_8m\nvisible_presenter_labels=13\nnamed_handoffs=13");
console.log(`xml_parts_valid=${deck.xmlParts}\nvisible_source_footers=13\nsource_footer_min_pt=10.5`);
console.log("note_sections_and_sources=13\npublic_delivery_choices=explicit\nprivate_meeting_urls=absent\nconceptual_slides=framework_neutral");
console.log("embedded_narrated_videos=1\nembedded_video_hash_match=true\nslide10_media_relationship=valid");

for (const rel of [
  "deck/generate.js",
  "deck/README.md",
  "demo/README.md",
  "demo/agent/equity_event/cli.py",
  "demo/agent/equity_event/live.py",
  "demo/agent/equity_event/ui_assets/index.html",
  "demo/agent/skills/event-date-alignment/SKILL.md",
  "demo/recording/README.md",
  "demo/recording/storyboard.json",
  "demo/media/equity-event-harness-demo.mp4",
  "demo/media/equity-event-harness-demo.metadata.json",
  "demo/sample-input/public-sources.json",
  "demo/sample-input/market-prices.json",
  "demo/sample-input/internal-policy.json",
  "demo/live-evidence/README.md",
  "demo/live-evidence/manifest.json",
  "README.md",
]) {
  if (!fs.existsSync(path.join(root, rel))) fail(`Missing deliverable: ${rel}`);
}

console.log(`pptx_bytes=${fs.statSync(pptx).size}`);
console.log("json=valid");
console.log("framework_pin=1.18.0_core\nprovider_pin=1.14.3_openai");
console.log("live_evidence=5_roles_valid\nnative_model_tool_correlation=valid\nskill_lifecycle=valid\ncross_run_memory=valid");
console.log("certificate_hashes=valid");
console.log("retained_episodes=valid");
console.log("deliverables=present");
