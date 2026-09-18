# Deck generation

The PowerPoint is generated with [PptxGenJS](https://gitbrent.github.io/PptxGenJS/) from `deck/generate.js`. Every diagram uses editable PowerPoint text, shapes, and connectors. No slide is a screenshot.

## Requirements

- Node.js 18 or later
- npm
- Windows PowerShell for OOXML validation; `ffprobe` for media validation
- Optional: Microsoft PowerPoint or LibreOffice for rendering

## Build

From the repository root:

```powershell
npm install
npm run build
```

Output:

```text
Modern-Agent-Harness-Engineering.pptx
```

If PowerPoint has the deck open, the build fails with `EBUSY`. Either close it, or
build and validate against a scratch path with the `DECK_OUT` override, which both
scripts honour:

```powershell
$env:DECK_OUT = "$env:TEMP\deck-verify.pptx"
npm run check
Remove-Item Env:\DECK_OUT
```

## Validate

```powershell
npm run validate
```

Validation checks:

- PPTX exists and is a non-trivial OOXML package.
- Exactly 13 slides and 13 speaker-note parts exist: 11 prepared, discussion, references.
- Every slide contains one `SOURCE:` footer at 10.5 pt or larger.
- Every note contains cumulative timing, presenter, segment, explanation, talk track, named handoff and citations with full public URLs.
- Prepared content ends at 30:00; slides 9–11 total five demo minutes. Discussion occupies a proposed 30:00–45:00 slot; references are untimed.
- Exact notes, README timings and speakers agree. All three names appear on the cover/agenda; each slide visibly labels its speaker.
- Known implementation claims include citations; the 1.18.0 core pin matches slide 9, notes and references.
- Slides 1–8 remain framework-neutral; citation markers have matching note entries. No research-statistics wall or financial A/B metrics are required.
- Live claims require retained native MAF tool spans, on-demand loading and cross-run memory evidence, not just matching slide text.
- `validate-live.js` correlates assistant-issued call IDs and arguments with native tool spans, verifies loaded instruction hashes and exact memory lineage, and checks certificate bytes. `npm run test:evidence` mutates the retained evidence to ensure fabricated loading/recall, missing checks and false certification are rejected offline.
- All OOXML and relationship parts parse successfully.
- All five curated runs have valid native trace, state and acceptance evidence; certified artifacts match their hashes, and the failed observe-only preview remains uncertified.
- the narrated MP4 has H.264 video and AAC audio, matches its Foundry provenance metadata, and is embedded and referenced by slide 10.
- Required repository deliverables are present.

Run build, validation and evidence mutation tests together:

```powershell
npm run check
```

## Optional rendering inspection

If PowerPoint is installed, open the deck and export to PDF. If LibreOffice is installed:

```powershell
New-Item -ItemType Directory -Force deck\rendered | Out-Null
soffice --headless --convert-to pdf --outdir deck\rendered Modern-Agent-Harness-Engineering.pptx
```

Render **all 13 slides**, inspect a slide-sorter montage, then inspect text bounds
and the denser slides 2, 4, 9, 11 and 13 at full size. Check citation and speaker
readability, connector direction, clipping and overlap. Start slide 10 in
PowerPoint slide-show mode and play the video; metadata validation alone is
not a playback test.

## Editing

All text remains editable in PowerPoint. Theme constants, helpers, notes, and slide content are centralized in `deck/generate.js`. Re-run the generator after source edits; do not hand-edit the generated deck if changes need to remain reproducible.

The embedded August 24 recording is retained as **legacy scripted fallback**.
It does not demonstrate the new editable console, live model/tool calls,
mid-run skill loading or cross-run memory. Slides 9–11 teach define → run →
observe using the live runtime; their notes separate the seeded offline
near-miss from nondeterministic live behavior. No new recording was made.

## Public presentation scope

The presentation follows history → components/autonomy → progressive tooling,
intelligent context and acceptance gates → five-minute walkthrough → discussion.
James owns history/walkthrough, Alexandre components/autonomy/acceptance, and
Kunwarpreet tooling/context. All facilitate discussion. The agenda exposes full
names and separate returning sections; each slide has a consistent presenter label.

**13 slides, 30+15 timing and the existing equity fixture are presentation
choices.** Prepared content includes a five-minute demo. Private planning material
and private repository links are excluded from this public snapshot.

Removed from prepared material: the five-verb teaching arc, standalone evolution,
proof-carrying research, memory virtualization, statistics, detailed financial
A/B story and reviewed-lesson segment. The original video remains available;
obsolete generated A/B examples and recording scripts have been removed.
The domain has an executable live-model path, scoped MAF memory and a local
configuration/observability console with an explicit offline fallback.
The narrative, speaker allocation and slide count are unchanged.

## Visual system

- **Background:** near-black/navy
- **Capability/context:** Microsoft blue and cyan
- **State:** violet
- **Verified/completed:** green
- **Policy/uncertainty:** amber
- **Failure:** coral
- **Typography:** Aptos Display / Aptos; 32 pt headings, mostly 18–28 pt diagram/body text, 10.5 pt source footers
- **Canvas:** 16:9 widescreen

Source footers, speaker labels and restrained diagrams provide consistent hierarchy.
