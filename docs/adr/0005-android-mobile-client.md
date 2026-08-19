# ADR 0005 — Native Android client with shared Guardian backend

## Status

Accepted for the maintained mobile branch.

## Context

Guardian separates contextual risk assessment, calibration, deterministic family policy, persistence, and enforcement from presentation. The Android branch must provide a native mobile interaction model without forking safety logic or silently expanding collection/device-control permissions.

`main` now also includes a hardened host runtime: adaptive observation, context buffering, ephemeral evidence handling, durable state, offline outbox, device heartbeat, diagnostics, native Swift ScreenCaptureKit/Vision integration, macOS packaging, and macOS E2E checks.

Those changes make the platform boundary more important. Reimplementing providers, calibration, thresholds, runtime recovery, or enforcement in Kotlin would create a second independently evolving safety/agent system.

## Decision

1. Keep `guardian_core/`, `risk_engine/`, `api/`, persistence, evaluation assets, fixtures, and device-command contracts canonical/shared.
2. Keep the product-facing mobile application native in Kotlin + Jetpack Compose under `android-app/`.
3. Consume the Guardian REST API directly from Android.
4. Keep classification, provider calls, calibration, safety controls, release gates, and family-policy evaluation on Python/shared code.
5. Keep `OPENAI_API_KEY` and all provider credentials outside Android.
6. Treat Android as a family review/control client in this slice: incidents, evidence metadata, reports, policy, device state, and explicit parent actions.
7. Register Android devices through `/api/devices/pair` with platform `Android`.
8. Use `/api/devices/{id}/heartbeat` for paired Android records, but truthfully report no screen-recording permission, no Accessibility permission, and no active observer.
9. Do not heartbeat `device-demo` from Android; it is the host-agent demo record.
10. Keep Android observation and enforcement unimplemented. The app requests only `INTERNET`.
11. Permit cleartext HTTP only in debug builds for emulator/LAN development. Release builds require encrypted transport.
12. Preserve independent Android CI while inheriting shared Python/web/R3 and macOS E2E CI from `main`.
13. Keep the deterministic fixture demo as the portable baseline. Host macOS visual/continuous observation may create incidents reviewed in Android, but does not make Android an observer.
14. Require a separate ADR and release gate before adding elevated Android permissions or real Android enforcement.

## Consequences

### Positive

- One source of truth for risk, calibration, policy, release gates, and incident contracts.
- Native Android UI without WebView or JavaScript runtime.
- No provider credentials in the APK.
- Upstream risk/evaluation improvements protect Android and browser flows equally because both consume the same API state.
- Host resilience improvements can evolve independently from Android lifecycle/permission choices.
- Paired Android devices can participate in the shared health model without falsely claiming observation capability.
- Android permissions remain narrow and auditable.

### Tradeoffs

- Android requires network access to the Guardian backend.
- Android does not currently produce observations or execute app blocks.
- Rich host observation/native helper capabilities are macOS-specific.
- The app summarizes visual evidence availability instead of adding an image-loading dependency in this slice.
- Authentication, multi-family isolation, encrypted production transport, and push notifications remain future work.

## Long-lived branch synchronization rule

`agent/android-mobile-port` is maintained as a long-lived branch. Upstream `main` changes should be merged, not copied as unrelated snapshots.

Conflict resolution follows these rules:

- shared backend/risk/agent code follows `main` unless an explicit mobile compatibility adaptation is required;
- Android UI/build files remain mobile-specific;
- mobile documentation is preserved and updated to describe inherited host capabilities accurately;
- provider credentials and safety decisions stay outside Kotlin;
- desktop/macOS permissions are never treated as implicit Android permissions;
- new API contracts are adopted in Android only when they accurately represent the mobile role.

## Future Android observation/enforcement

Real Android observation/enforcement requires a separate ADR and release gate. It must choose a legitimate Android management model, define protected/system-package rules, handle explicit consent and revocation, document Android/Play-policy implications, define offline/recovery behavior for Android specifically, and update privacy/threat models before any elevated permission is introduced.
