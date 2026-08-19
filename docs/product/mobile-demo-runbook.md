# Android mobile demo runbook

This runbook adapts the current Guardian demo flow to the maintained Android branch, `agent/android-mobile-port`.

The Android application is the **parent/family review interface**. Risk classification, calibration, policy evaluation, incident creation, evidence persistence, and device-command handling remain host/backend responsibilities.

## Demo modes

### Recommended: deterministic fixture + Android review

This is the portable, reproducible mobile demo.

- no OpenAI key;
- no external service;
- no Android elevated permission;
- no Android screen capture;
- no real Android enforcement.

Flow:

```text
controlled fixture
    ↓
Python risk + policy pipeline
    ↓
Guardian API incident
    ↓
Android parent review
    ↓
unlock / keep blocked
    ↓
host demo-agent command acknowledgement
```

### Optional: one-shot macOS visual demo + Android review

The synchronized upstream backend also supports an optional host-side visual path.

- screenshot capture occurs on macOS;
- OpenAI classification occurs from the Python host/provider layer;
- `OPENAI_API_KEY` stays on the host;
- Android reviews the resulting incident through the same API;
- Android still does not capture the screen or enforce app blocks.

The upstream browser-oriented runbook remains available at `docs/product/demo-runbook.md`.

---

# Preparation

## 1. Check out the mobile branch

```bash
git fetch origin
git switch agent/android-mobile-port
git pull
```

## 2. Bootstrap Python

### macOS / Linux

```bash
bash scripts/bootstrap.sh
```

### Windows PowerShell

```powershell
.\scripts\bootstrap.ps1
```

## 3. Reset old demo state

With the API stopped:

### macOS / Linux

```bash
bash scripts/reset-demo.sh
```

### Windows PowerShell

```powershell
.\scripts\reset-demo.ps1
```

## 4. Verify the current risk regression gate

```bash
.venv/bin/python scripts/run_r3_evals.py --check
```

For the complete repository check, install the Node/pnpm dependencies and run `scripts/check.sh` or `scripts/check.ps1`.

## 5. Prepare Android

Use an Android Emulator for the simplest presentation path.

Expected Android toolchain:

- JDK 17;
- Android SDK 36;
- Gradle 8.13 for command-line builds;
- `android-app` as the application module.

The emulator app defaults to:

```text
http://10.0.2.2:8000
```

Keep the mobile app configured for `device-demo` during the canned demo so it refers to the same device as the host-side fixture launcher.

---

# Deterministic Android demo

## Terminal 1 — start the API

### macOS / Linux

```bash
bash scripts/run-api.sh
```

### Windows PowerShell

```powershell
.\scripts\run-api.ps1
```

Host endpoints:

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/demo-chat
```

## Android — start the app

Build/run from Android Studio, or build the debug APK with:

```bash
gradle :android-app:assembleDebug
```

In **Conexão** confirm:

```text
API: http://10.0.2.2:8000
device: device-demo
```

Use the connection check before starting the incident.

## Terminal 2 — trigger the fixture

### macOS / Linux

```bash
bash scripts/run-demo.sh
```

### Windows PowerShell

```powershell
.\scripts\run-demo.ps1
```

Expected host behavior:

1. `fixtures/dangerous_contact/session.json` is loaded.
2. The recent context is classified.
3. Family policy is evaluated separately from classification.
4. Runtime release gates are applied.
5. The block is simulated.
6. The incident and minimal evidence are persisted.
7. The agent waits for a parent command.

Useful terminal lines include:

```text
assessment=...
decision=...
incident=...
parent_view=...
child_view=...
```

## Android — review and decide

1. Open **Início**.
2. Tap **Atualizar** if the new incident is not already listed.
3. Open the incident.
4. Review category, confidence, explanation, evidence summary, and status.
5. Choose **Desbloquear aplicativo** or **Manter bloqueado**.

When unlock is chosen, the backend creates an `UNLOCK_APPLICATION` command for `device-demo`.

Terminal 2 should eventually confirm:

```text
unlocked=Guardian Demo Chat command=<id>
```

That line completes the end-to-end command cycle.

---

# Optional visual demo with Android as parent UI

This mode is optional and currently requires a macOS host.

## Requirements

- Guardian API running locally;
- controlled synthetic demo content;
- macOS screen-capture permission for the observer;
- an OpenAI API key if the optional OpenAI path is used.

Set the key on the host only:

```bash
export OPENAI_API_KEY="..."
```

Do not put the key in Android settings, Gradle configuration, source code, or the APK.

## Start the controlled chat

Open:

```text
http://127.0.0.1:8000/demo-chat
```

Reveal the controlled dangerous-contact progression until the frame is ready for capture.

## Trigger the launcher

```bash
bash scripts/run-live-demo.sh
```

The launcher prints its mode/source explicitly. Depending on local capability it may use the optional live path or fall back to the deterministic fixture path.

If the visual path succeeds, the host agent uploads selected screenshot evidence to the same incident API. The Android incident contract is unchanged; the mobile UI can still review the incident and reports that visual evidence is available on the server.

Complete the parent decision in Android exactly as in the deterministic flow.

---

# Physical Android device

A physical phone cannot use emulator alias `10.0.2.2`.

Bind the API to the development machine's network interface:

### macOS / Linux

```bash
.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Configure Android with the host LAN address, for example:

```text
http://192.168.1.50:8000
```

Checklist:

- phone and development machine are on the same trusted network;
- TCP port 8000 is allowed through the host firewall;
- wireless client isolation is disabled;
- the app is a debug build if using local cleartext HTTP.

Use HTTPS outside trusted local development.

---

# Device pairing

The Android app may register itself through:

```http
POST /api/devices/pair
```

The returned device ID is persisted locally by the app.

For the canned host-agent demo, however, switch back to **Usar dispositivo demo** so the app and `scripts/run-demo.sh` both target `device-demo`.

Pairing currently means registration only. It does not activate Android observation, screen capture, or enforcement.

---

# Failure recovery

## Android cannot reach the API

- Emulator: verify the app uses `http://10.0.2.2:8000`.
- Physical device: verify the LAN IP, `0.0.0.0` binding, firewall, and network isolation.
- Confirm `http://127.0.0.1:8000/api/health` works on the host.

## Old or duplicate incident

Stop the API, reset state, restart the API, and repeat:

```bash
bash scripts/reset-demo.sh
```

## Optional visual demo fails

Keep the error visible and use the deterministic fixture path. The fixture path is an explicit supported demo source, not a hidden degraded mode.

## Android is paired to a different device

Use **Conexão → Usar dispositivo demo** before running the canned fixture.

---

# Presentation boundaries

During the mobile demo, state these boundaries accurately:

- Android is native Compose, not a WebView wrapper.
- Android does not contain the risk engine or provider credentials.
- Classification and calibration occur in the shared Python pipeline.
- The standard Android demo is deterministic and local.
- The optional OpenAI visual path is host-side and macOS-specific.
- Android currently has no continuous observation or real enforcement capability.
- Android requests only internet access.
- A real Android enforcement model requires a separate architecture decision and release gate.
