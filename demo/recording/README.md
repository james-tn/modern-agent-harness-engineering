# Legacy recording provenance

The August 24 recording is a **164-second scripted fallback** embedded on
slide 10, not a recording of the current live console. It does not demonstrate
live model calls, model-driven skill loading or cross-run memory. Its approval
is scripted, not a live human decision.

Preserved unchanged: [MP4](../media/equity-event-harness-demo.mp4),
[cover](../media/equity-event-harness-demo-cover.png),
[provenance metadata](../media/equity-event-harness-demo.metadata.json) and
[storyboard](storyboard.json). The metadata records Microsoft Foundry
`gpt-4o-mini-tts` narration, voice `onyx`, request fingerprints and artifact hashes.
`npm run validate` checks those hashes and the slide's embedded media.

The obsolete recorder scripts and npm recording command were retired; their
historical versions remain in Git history. No new recording was made.
Use the [demo guide](../README.md) for the current live/offline workflow.
