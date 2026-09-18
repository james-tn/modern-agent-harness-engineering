# Editable slide tooling

The [PowerPoint](../Modern-Agent-Harness-Engineering.pptx) is generated with
[PptxGenJS](https://gitbrent.github.io/PptxGenJS/) from `generate.js`.
Diagrams use editable text, shapes and connectors, rather than slide screenshots.
For the concepts and demo behavior, start with the [main guide](../README.md)
and [demo guide](../demo/README.md).

## Build

Requirements: Node.js 18 or later and npm. The full validator also requires
Windows PowerShell and `ffprobe` from FFmpeg. From the repository root:

```powershell
npm ci
npm run build
```

The output is `Modern-Agent-Harness-Engineering.pptx`. Close it in PowerPoint
before rebuilding, or use a scratch output:

```powershell
$env:DECK_OUT = "$env:TEMP\deck-verify.pptx"
npm run check
Remove-Item Env:\DECK_OUT
```

## Validate

```powershell
npm run validate
npm run test:evidence
```

Validation covers the OOXML package, slide/note relationships, citations,
embedded video hashes, framework pins and consistency of the presentation.
Audience documentation must describe the concepts and demo without delivery
logistics.

The retained-evidence validator correlates model-issued calls with native tool
spans, checks loaded instruction hashes and cross-run memory lineage, recomputes
returns, and validates acceptance, approval and certificate bytes. Mutation tests
reject fabricated loading/recall, missing checks and false certification.

`npm run check` combines generation, validation and evidence tests.

## Editing and visual inspection

Theme constants, helpers, notes and slide content are in `generate.js`. Rebuild
after source changes so the editable artifact stays reproducible.

For visible changes, render the slides with PowerPoint or LibreOffice and inspect
text bounds, clipping, connectors and citation readability. Test video playback
in PowerPoint; metadata validation alone is not a playback test.

The deck uses a dark 16:9 canvas, Aptos typography, editable diagrams and a single
visual hierarchy. Capability/context is blue/cyan, state violet, verified results
green, policy/uncertainty amber and failures coral.

The embedded recording is a preserved **legacy scripted example**, not evidence
of the current live console, model-issued skill loading or cross-run memory.
