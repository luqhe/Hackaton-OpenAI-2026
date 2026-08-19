# Guardian Android

Native Android **Family/Membership client** for the Guardian mobile branch.

The app is written in Kotlin/Jetpack Compose and consumes the shared Guardian API. It is not a WebView and it is not the protected Device agent.

## Responsibilities

Android handles:

- Account login and Family session state;
- in-memory session/cookie + CSRF handling;
- Family-scoped incident review;
- unlock / keep-blocked decisions;
- Child daily report and policy editing;
- protected Device status display;
- issuing short-lived Device pairing challenges;
- explicit local synthetic demo mode.

Android does **not** handle:

- risk classification or calibration;
- OpenAI/provider credentials;
- screen observation or OCR;
- Accessibility enforcement;
- protected Device private/signing credentials;
- `/api/agent/*` Device protocol execution.

A protected Device is a separate identity. The family app can create its pairing code, but the Device generates its own key and receives/stores its own credential.

## Specifications

- Kotlin `2.3.21`
- Jetpack Compose + Material 3
- Compose BOM `2026.06.00`
- Activity Compose `1.10.1`
- Android Gradle Plugin `8.13.2`
- Gradle `8.13` in CI
- Java 17
- `compileSdk = 36`
- `targetSdk = 36`
- `minSdk = 26`
- Application ID `com.guardian.mobile`
- Version `0.1.0`
- Permission: `INTERNET` only

Debug builds allow cleartext HTTP for local development. Release builds disable cleartext transport.

## Family authentication

Normal mode uses the R2 session contract:

1. `POST /api/auth/login`
2. capture `guardian_session` and `guardian_csrf`
3. send cookies on subsequent requests
4. send `X-CSRF-Token` on mutations
5. clear the session on logout/401

The Android implementation deliberately keeps session cookies and the password in memory only. They are not written to `SharedPreferences`.

The persisted non-secret preferences are:

- API URL;
- local-demo toggle;
- selected Child ID;
- last resolved Device ID.

## Device pairing

From an authenticated family session, Android can call:

```http
POST /api/pairing/challenges
```

and display the returned short code. The protected Device separately completes:

```http
POST /api/device/pair
```

and then uses its signed `/api/agent/*` protocol. The Android family app never receives the Device secret.

## Recommended local demo

The secure demo is explicit and loopback-only.

### 1. Start backend demo mode

macOS/Linux:

```bash
bash scripts/run-mobile-demo-api.sh
```

Windows:

```powershell
.\scripts\run-mobile-demo-api.ps1
```

### 2. Forward Android localhost

```bash
adb reverse tcp:8000 tcp:8000
```

### 3. Run Android

Build from Android Studio or:

```bash
gradle :android-app:assembleDebug
```

In **Configuração** use:

```text
API URL: http://127.0.0.1:8000
Modo de demonstração local: ON
Child ID: child-demo
```

Use `device-demo` for the canned fixture flow.

### 4. Trigger the fixture

macOS/Linux:

```bash
bash scripts/run-mobile-demo.sh
```

Windows:

```powershell
.\scripts\run-mobile-demo.ps1
```

Refresh the Android dashboard, open the incident, and choose unlock or keep blocked.

The server and fixture launcher both set `GUARDIAN_DEMO_MODE=true`. The Android toggle adds `X-Guardian-Demo: true`. The backend still validates that this is a development/test, local-transport request.

## Normal/non-demo use

Disable demo mode and configure the real API URL. For non-local deployments use HTTPS.

An existing Account/Membership must already be provisioned server-side. Login with email/password and optionally `family_id`, then configure the Child ID belonging to that Family.

## Android permissions

This module intentionally does not request:

- screen capture;
- Accessibility;
- microphone;
- camera;
- notification access;
- Device Admin / Device Owner.

Those would belong to a future Android protected-device agent and require a separate ADR/release gate.

See the full branch guide in [`../README.md`](../README.md) and the mobile demo runbook in [`../docs/product/mobile-demo-runbook.md`](../docs/product/mobile-demo-runbook.md).
