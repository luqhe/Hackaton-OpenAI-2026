# ADR 0005 — Native Android client with shared Guardian backend

## Status

Accepted for the maintained mobile branch.

## Context

Guardian separates contextual risk assessment, calibration, deterministic family policy, persistence, and enforcement from the presentation layer. The Android branch must provide a native mobile interaction model without forking the safety decision logic or silently expanding collection/device-control permissions.

Since the original Android port was created, `main` added a broader R3 risk stack: normalized context contracts, provider abstractions, category calibration, configurable risk controls, evaluation/regression gates, shadow-mode outputs, and an optional OpenAI multimodal provider used by a controlled one-shot macOS demo.

Those changes increase the importance of preserving a single safety pipeline. Reimplementing provider selection, calibration, thresholds, kill switches, or policy behavior in Kotlin would create two independently evolving safety systems.

## Decision

1. Keep `guardian_core/`, `risk_engine/`, `api/`, persistence, evaluation assets, fixtures, and the device-command protocol as canonical shared/backend components.
2. Keep the product-facing mobile application native in Kotlin and Jetpack Compose under `android-app/`.
3. Consume the Guardian REST API directly from Android.
4. Keep risk classification, provider calls, calibration, safety controls, release gates, and family-policy evaluation on the Python side.
5. Do not place `OPENAI_API_KEY` or any provider credential in the Android app. Optional OpenAI classification remains host/backend-side.
6. Treat Android as a family review/control client in this slice: it renders incidents, evidence metadata, reports, policy, device state, and explicit parent actions.
7. Pair Android devices through `/api/devices/pair` with platform `Android`, while keeping `device-demo` available for the reproducible host-agent demo.
8. Keep Android enforcement simulated/not implemented. The app requests only `INTERNET`.
9. Permit cleartext HTTP only in debug builds for emulator/LAN development. Release builds require encrypted transport.
10. Preserve independent Android CI while also inheriting the shared Python/web/R3 CI from `main`.
11. Keep the deterministic fixture demo as the portable baseline. The optional one-shot visual demo may create incidents reviewed in Android, but screen capture remains a host macOS concern.
12. Require a separate ADR and release gate before Android gains observation or enforcement permissions.

## Consequences

### Positive

- One source of truth for risk, calibration, policy, and release-gate behavior.
- Native Android UI without a JavaScript runtime or WebView.
- No provider credentials in the mobile application.
- Upstream R3 evaluation and safety controls automatically protect both browser and Android review flows because both consume the same incidents.
- Existing fixtures and host-agent tests remain useful for the Android demo.
- Android permissions remain narrow and auditable.
- Device pairing can evolve independently of `device-demo`.

### Tradeoffs

- The Guardian backend must be reachable from the Android device.
- Android currently cannot produce its own observations or enforce app blocks.
- The optional visual demo is macOS-specific even when Android is used for parent review.
- The mobile UI currently summarizes visual-evidence availability rather than introducing an image-loading dependency.
- Authentication, multi-family isolation, encrypted production transport, and push notifications remain future work.

## Synchronization rule

`agent/android-mobile-port` is maintained as a long-lived branch. Upstream `main` changes should be merged into it rather than copied as unrelated snapshots. Conflicts should preserve these boundaries:

- shared risk/policy/backend logic follows `main` unless a mobile-specific compatibility issue requires an explicit adaptation;
- Android UI/build files remain mobile-specific;
- provider credentials and safety decision logic stay outside Kotlin;
- new Android permissions are never inherited implicitly from desktop capabilities.

## Future real-device enforcement

Real Android enforcement must be a separate ADR and release gate. It should select a legitimate Android management model, define protected/system-package deny rules, handle explicit consent and revocation, document Android/Play policy implications, add tamper-resistance expectations, and update the privacy/threat models before any elevated permission is introduced.
