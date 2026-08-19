# ADR 0005 — Native Android Family client over shared Guardian security domain

## Status

Accepted and updated after the R2 Family/Device security merge.

## Context

Guardian now separates two authenticated actors:

1. **Family actors** — Account + active Membership inside exactly one Family scope.
2. **Protected Devices** — Device identities assigned to a Child and authenticated with their own signed Device credentials.

The maintained Android application is the family-facing mobile interface. It must not reuse protected-device secrets or collapse the Family and Device trust boundaries just because both communicate with the same API.

The shared backend also owns contextual risk assessment, calibration, policy, evidence, audit, lifecycle, rate limiting, and the protected-device command protocol.

## Decision

1. Keep `api/`, `guardian_core/`, `risk_engine/`, data-security controls, identity, and the Device protocol canonical on the shared Python/backend side.
2. Keep the Android UI native Kotlin + Jetpack Compose; do not use a WebView.
3. Model Android as a **Family/Membership client**, not as the protected Device agent.
4. Authenticate normal Android sessions with `/api/auth/login` and the server's `guardian_session` + `guardian_csrf` cookie contract.
5. Keep the session cookie, CSRF token, and password in memory only. Do not persist them in `SharedPreferences`.
6. Send `X-CSRF-Token` on authenticated family mutations.
7. Respect Family scope from the authenticated session. Child, Device, incident, and evidence identifiers never create or broaden authorization.
8. Let Android issue one-time Device pairing challenges through `/api/pairing/challenges`.
9. Let the protected Device separately generate key material, complete `/api/device/pair`, and own its issued signed Device credential.
10. Never expose the Device secret to the Android Family app.
11. Keep protected-device `/api/agent/*` signing/command behavior out of the Android Family client.
12. Preserve a synthetic local demo only through explicit `GUARDIAN_DEMO_MODE=true` plus `X-Guardian-Demo: true` and the backend's local-transport validation.
13. Use `adb reverse tcp:8000 tcp:8000` for the recommended Android demo so the API remains bound to host loopback instead of opening demo authorization to the LAN.
14. Request only Android `INTERNET` permission in this family client.
15. Keep cleartext HTTP debug-only; release builds require encrypted transport.
16. Keep an independent Android CI build in addition to the shared Python/web/security CI.

## Consequences

### Positive

- Family and protected-Device identities remain cryptographically and conceptually separate.
- Android benefits from the new R2 authentication, tenant isolation, CSRF, audit, rate-limit, evidence, and data-lifecycle controls without reimplementing them.
- The mobile app cannot accidentally leak a Device signing secret because it never receives one.
- A stolen Android process session is limited to the server-issued Family session rather than becoming a protected-device credential.
- The deterministic hackathon demo remains possible but is visibly and technically separated from normal authentication.
- Backend/risk changes can continue to follow `main` without forking the safety decision logic into Kotlin.

### Tradeoffs

- The Android process does not persist authentication, so users must log in again after process death/restart.
- The first mobile slice requires a manually configured Child ID because the current shared API does not yet expose a dedicated Family-children discovery endpoint for the app.
- Pairing requires cooperation from a separate protected Device enrollment flow; the family app cannot self-enroll as the protected endpoint.
- Local demo networking requires ADB reverse rather than the simpler emulator `10.0.2.2` path so the new loopback-only demo boundary remains intact.
- The Android UI currently reports protected visual evidence availability but does not add a third-party image-loading stack in this slice.

## Security boundaries

The Android Family app must not claim or request:

- screen observation;
- Accessibility enforcement;
- microphone/camera capture;
- Device Admin / Device Owner control;
- protected Device signing credentials;
- OpenAI/provider credentials.

Normal Family mutations require the authenticated server session and CSRF token. Demo-mode authorization is not a fallback for failed production authentication; it must be explicitly configured and is forbidden in staging/production.

## Future Android protected-device agent

A future Android protected-device component must be a separate architecture decision. At minimum it must define:

- Device key generation/storage (preferably hardware-backed where available);
- pairing confirmation UX;
- signed request canonicalization and replay handling;
- credential rotation/revocation;
- background execution constraints;
- legitimate observation/enforcement APIs;
- protected/system package deny rules;
- consent and revocation;
- Play-policy implications;
- tamper resistance;
- evidence minimization;
- privacy/threat-model changes;
- release gates and false-positive controls.

It must not simply add elevated permissions to the existing Family app.
