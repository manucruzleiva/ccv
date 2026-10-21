# Project Goal — CCV (Capture Card Viewer)

## Mission
Provide a lightweight Windows desktop application that lets people play a console through a USB capture card in a normal desktop window, without needing to configure a streaming studio or depend on a clumsy vendor utility.

## User Value
A user should be able to connect a compatible capture card, open CCV, see and hear the console with practical low latency, and start playing quickly. Recording a clip and capturing a screenshot should be available when wanted, not require a separate production workflow.

## Product Scope
Deliver a portable Windows application with device discovery and selection, embedded video and audio preview, sensible playback controls, screenshot capture, optional video recording, and a simple user interface. Package required runtime components so a user can run the application without installing a development environment or assembling external dependencies.

## Quality Principles
- Optimize for quick startup, low idle resource use, and responsive preview.
- Keep the default workflow obvious: open, select if necessary, play, capture when needed.
- Handle missing devices, unsupported formats, device disconnects, audio failures, and recording errors without crashing or losing unrelated work.
- Keep recording and screenshot output locations clear and user-controlled.
- Avoid unnecessary overlays, streaming-oriented complexity, telemetry, advertisements, and account requirements.
- Be transparent about supported hardware, Windows requirements, and known limitations.

## Success Criteria
- A new user can reach a working preview with minimal setup.
- Audio and video remain synchronized and stable during ordinary play sessions.
- Screenshots and recordings are saved correctly and failures are reported clearly.
- The application remains lightweight during idle and active use.
- Portable releases are reproducible, include required runtime dependencies, and can be tested on supported Windows versions.

## Boundaries
CCV is a viewer and capture utility, not a console emulator, game-streaming service, or replacement for every professional broadcast workflow. Compatibility depends on capture-card drivers and device capabilities. Favor a reliable, focused playing experience over feature accumulation.