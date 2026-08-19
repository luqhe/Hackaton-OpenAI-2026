# Guardian Android

Native Android family client for Guardian on branch `agent/android-mobile-port`.

The Android application is deliberately a **review/control client**, not a second risk or enforcement agent. Context processing, provider calls, calibration, family policy, release gates, incidents, evidence, and host command execution remain in the shared Python backend.

## Stack

- Kotlin 2.3.21
- Jetpack Compose + Material 3
- Compose BOM `2026.06.00`
- Android Gradle Plugin 8.13.2
- Gradle 8.13 in CI
- Java 17
- `compileSdk` / `targetSdk` 36
- `minSdk` 26
- FastAPI Guardian backend

The app does not use a WebView and never stores `OPENAI_API_KEY`.

## Mobile flows

- Parent dashboard and daily metrics.
- Incident review and evidence summary.
- Unlock / keep-blocked decisions.
- Child transparency view.
- Family policy editor.
- API connection settings.
- Android device registration.
- Conservative heartbeat for paired Android devices.
- Backend capability disclosure.

## Android heartbeat

The synchronized backend now exposes `POST /api/devices/:id/heartbeat`.

After a phone is paired, the Android client uses it to update the device's `last_seen_at`. The payload intentionally reports the current implementation boundary:

```text
screen recording permission: false
Accessibility permission:    false
observer healthy:             false
offline queue depth:          0
```

The legacy `device-demo` record is not heartbeated by Android because it represents the host-side demo agent.

## Permissions

The manifest requests only `INTERNET`.

This port does not currently enable:

- Accessibility Service;
- MediaProjection / continuous Android screen capture;
- microphone or camera;
- Notification Listener;
- Device Administrator / Device Owner;
- real Android app blocking.

Those capabilities require a separate Android architecture/release-gate decision.

## Shared functionality inherited from `main`

The mobile branch now tracks the current shared stack, including:

- contextual risk contracts and R3 calibration/evaluation;
- optional host-side OpenAI provider;
- risk controls, frozen regression gates, and shadow-mode reports;
- adaptive host observation and context buffering;
- durable state, command recovery, offline outbox, heartbeat and diagnostics;
- ephemeral evidence lifecycle;
- native Swift ScreenCaptureKit/Vision helper;
- macOS packaging and E2E checks.

These are shared/backend or host/macOS features. They do not grant equivalent permissions to Android.

## Deterministic local demo

Start the backend:

```bash
bash scripts/bootstrap.sh
bash scripts/run-api.sh
```

Run Guardian on an Android Emulator. The default API URL is:

```text
http://10.0.2.2:8000
```

Build with Android Studio or:

```bash
gradle :android-app:assembleDebug
```

Keep `device-demo` selected for the canned fixture flow, then run:

```bash
bash scripts/run-demo.sh
```

Refresh **Início**, open the incident, and make the parent decision. Unlocking should eventually produce a host-agent line similar to:

```text
unlocked=Guardian Demo Chat command=<id>
```

## Optional host visual/continuous paths

The synchronized repository also has macOS host observation paths, including `run-live-demo.sh` and `agent.main observe`.

Android can review incidents created by those paths, but the phone does not perform their screen capture or provider calls.

## Physical device

Bind FastAPI to a LAN interface:

```bash
.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Then configure **Conexão** with the host LAN address, for example:

```text
http://192.168.1.50:8000
```

Debug builds allow local cleartext HTTP. Release builds require HTTPS.

For the full setup and demo workflow, see:

- [`../README.md`](../README.md)
- [`../docs/product/mobile-demo-runbook.md`](../docs/product/mobile-demo-runbook.md)
- [`../docs/adr/0005-android-mobile-client.md`](../docs/adr/0005-android-mobile-client.md)
