# ADR 0005 — Native Android client with shared Guardian backend

## Status

Accepted for the mobile hackathon port.

## Context

The original Guardian vertical slice separates contextual risk assessment, deterministic family policy and persistence from the presentation layer. The browser UI is served by FastAPI, while operating-system enforcement is isolated behind the edge-agent enforcer.

An Android port should provide a real mobile interaction model without forking the safety decision logic or turning the app into a WebView wrapper. It also must not silently expand collection or device-control permissions merely because Android exposes those APIs.

## Decision

1. Keep `guardian_core/`, `risk_engine/`, `api/`, storage, fixtures and the device-command protocol as the canonical backend.
2. Add a native `android-app/` written in Kotlin and Jetpack Compose.
3. Consume the existing REST API directly from Android.
4. Keep risk classification and policy evaluation on the Python side; Kotlin renders state and invokes explicit user actions only.
5. Pair Android devices through the existing `/api/devices/pair` contract with platform `Android`.
6. Keep enforcement simulated in this port. The app requests only `INTERNET`.
7. Permit cleartext HTTP only in debug builds for the local emulator demo. Release builds require encrypted transport.
8. Add an independent Android CI job so mobile build health does not weaken the existing Python/web checks.

## Consequences

### Positive

- One source of truth for policy and safety behavior.
- Native mobile UI and navigation without a JavaScript runtime or WebView.
- Existing fixtures and backend tests remain useful for the mobile demo.
- Android permissions stay narrow and auditable.
- Device pairing can evolve independently of the demo `device-demo` record.

### Tradeoffs

- The backend still needs to be reachable from the Android device.
- This version does not perform continuous on-device observation or real app blocking.
- Authentication and multi-family isolation remain required before public deployment.
- Evidence images are summarized in the native UI rather than rendered with a new image-loading dependency in the first mobile slice.

## Future real-device enforcement

Real Android enforcement must be a separate ADR and release gate. It should select a legitimate Android management model, define protected/system-package deny rules, handle explicit consent and revocation, document Play policy implications, and update the privacy/threat models before permissions are added.
