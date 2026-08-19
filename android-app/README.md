# Guardian Android

Native Android client for the Guardian hackathon MVP on branch `agent/android-mobile-port`.

The app is intentionally a **family review/control client**, not a second risk engine. The synchronized Python backend owns contextual risk assessment, calibration, provider selection, deterministic policy, incident persistence, evidence, release gates, evaluation, and device commands.

## Stack

- Kotlin 2.3.21
- Jetpack Compose + Material 3
- Compose BOM `2026.06.00`
- Android Gradle Plugin 8.13.2
- Gradle 8.13 in CI
- Java 17
- `compileSdk` / `targetSdk` 36
- `minSdk` 26
- Existing FastAPI Guardian backend

The app does not use a WebView and does not call OpenAI directly.

## What the app provides

- Parent dashboard and daily metrics.
- Incident review and evidence summary.
- Unlock / keep-blocked parent decisions.
- Child transparency view.
- Family policy editing.
- API connection settings.
- Android device registration/pairing.
- Capability disclosure from the backend.
- Compatibility with incidents generated from deterministic fixtures or the optional host-side one-shot visual demo.

## Permissions and enforcement

The manifest requests only `INTERNET`.

This port does not currently enable:

- Accessibility Service;
- MediaProjection / continuous Android screen capture;
- microphone or camera;
- Notification Listener;
- Device Administrator / Device Owner;
- real Android app blocking.

Those features require a separate Android enforcement architecture, consent/revocation model, privacy/threat-model update, package safety rules, and release gate.

## Backend changes inherited from `main`

The mobile branch now includes the current upstream R3 backend work:

- normalized context/contracts;
- provider abstraction and optional OpenAI multimodal provider;
- category calibration and risk controls;
- frozen evaluation/regression gates;
- shadow-mode reports;
- controlled `/demo-chat`;
- optional macOS `live-demo` path;
- expanded risk/live-demo tests and CI checks.

None of those changes move provider credentials or safety decisions into Android.

## Run the deterministic demo

Start the backend on the development machine:

```bash
bash scripts/bootstrap.sh
bash scripts/run-api.sh
```

The Android Emulator can reach the host API at:

```text
http://10.0.2.2:8000
```

Build with Android Studio or, with Gradle 8.13 installed:

```bash
gradle :android-app:assembleDebug
```

Run the app on the emulator, open **Conexão**, keep the API URL at `http://10.0.2.2:8000`, and use `device-demo` for the canned fixture flow.

In another terminal:

```bash
bash scripts/run-demo.sh
```

Refresh **Início**, review the incident, and choose the parent decision. Unlocking should eventually produce `unlocked=Guardian Demo Chat` in the host-side agent terminal.

## Optional host-side visual demo

On macOS, the synchronized backend also supports:

```bash
export OPENAI_API_KEY="..."
bash scripts/run-live-demo.sh
```

That path captures/classifies a selected frame on the host Mac. Android still only reviews the resulting Guardian incident; it does not capture the screen or receive the OpenAI key.

## Physical Android device

Bind FastAPI to the LAN instead of loopback:

```bash
.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Then configure **Conexão** with the host's LAN IP, for example:

```text
http://192.168.1.50:8000
```

Debug builds allow local cleartext HTTP. Release builds disable cleartext transport; use HTTPS outside trusted local development.

For the full branch setup, risk/evaluation checks, and demo instructions, see the repository root [`README.md`](../README.md) and [`docs/product/mobile-demo-runbook.md`](../docs/product/mobile-demo-runbook.md).
