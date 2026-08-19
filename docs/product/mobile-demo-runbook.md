# Android mobile demo runbook

This runbook adapts the current Guardian demo flow to the maintained Android branch, `agent/android-mobile-port`.

The Android application is the **parent/family review interface**. Risk classification, calibration, policy evaluation, incident creation, evidence persistence, and host command execution remain backend/host responsibilities.

## Demo modes

### Recommended: deterministic fixture + Android review

This is the portable, reproducible mobile demo.

- no OpenAI key;
- no external service;
- no elevated Android permission;
- no Android screen capture;
- no real Android enforcement.

```text
controlled fixture
    ↓
shared Python risk + calibration + policy pipeline
    ↓
Guardian API incident
    ↓
Android parent review
    ↓
unlock / keep blocked
    ↓
host demo-agent command acknowledgement
```

### Optional: macOS observation + Android review

The synchronized host runtime also supports controlled one-shot and continuous macOS observation paths.

- capture/observation occurs on macOS;
- optional OpenAI provider calls occur from Python on the host;
- `OPENAI_API_KEY` stays on the host;
- Android reviews the resulting incident through the same API;
- Android does not inherit macOS capture, OCR, Accessibility, or enforcement capabilities.

See `docs/product/macos-permissions.md` before enabling host observation.

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
3. Calibration/risk controls and family policy remain separate from classification.
4. Runtime release gates are applied.
5. The block is simulated.
6. The incident and minimal evidence are persisted.
7. The host agent waits for a parent command.

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
2. Tap **Atualizar** if the incident is not already listed.
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

# Optional host visual demo with Android as parent UI

This mode currently requires a macOS host.

## Requirements

- Guardian API running locally;
- controlled synthetic demo content;
- required macOS capture permissions;
- an OpenAI API key if the optional OpenAI path is used.

Set the key on the host only:

```bash
export OPENAI_API_KEY="..."
```

Do not put it in Android settings, Gradle configuration, source code, or APK resources.

Open the controlled chat:

```text
http://127.0.0.1:8000/demo-chat
```

Then trigger:

```bash
bash scripts/run-live-demo.sh
```

The launcher reports its source/mode explicitly and may fall back to the deterministic fixture path. If a visual incident is created, refresh Android and review it through the same incident contract.

The current Android UI reports when visual evidence is available on the server; it does not introduce Android capture or an image-loading dependency.

## Optional continuous host observation

The latest synchronized host runtime also provides:

```bash
.venv/bin/python -m agent.main observe
```

That path uses the host/macOS observation stack, including adaptive scheduling, temporal context buffering, ephemeral evidence, durable state, offline outbox, heartbeat, diagnostics, and recovery behavior.

This does **not** turn the Android app into an observer.

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

# Android device pairing and heartbeat

The Android app can register itself through:

```http
POST /api/devices/pair
```

The returned device ID is persisted locally.

For an actually paired Android record, the client also calls:

```http
POST /api/devices/:id/heartbeat
```

The heartbeat updates liveness while deliberately reporting the current mobile boundary:

```text
screen_recording_permission = false
accessibility_permission    = false
observer_healthy            = false
offline_queue_depth         = 0
```

Pairing + heartbeat do **not** activate Android observation, screen capture, OCR, Accessibility, or enforcement.

For the canned host-agent demo, use **Conexão → Usar dispositivo demo** so Android and `scripts/run-demo.sh` both target `device-demo`. Android does not heartbeat that legacy demo record.

---

# Failure recovery

## Android cannot reach the API

- Emulator: verify `http://10.0.2.2:8000`.
- Physical device: verify the LAN IP, `0.0.0.0` binding, firewall, and network isolation.
- Confirm `http://127.0.0.1:8000/api/health` works on the host.

## Old or duplicate incident

Stop the API, reset state, restart it, and repeat:

```bash
bash scripts/reset-demo.sh
```

## Optional host observation fails

Keep the error visible and use the deterministic fixture path. The fixture path is an explicit supported demo source, not a hidden degraded mode.

## Android is paired to a different device

Use **Conexão → Usar dispositivo demo** before running the canned fixture.

---

# Presentation boundaries

State these accurately during the mobile demo:

- Android is native Compose, not a WebView wrapper.
- Android does not contain the risk engine or provider credentials.
- Classification, calibration, and policy occur in the shared Python pipeline.
- The standard Android demo is deterministic and local.
- OpenAI and richer observation paths are host-side.
- The synchronized native Swift helper and macOS packaging are host capabilities, not Android capabilities.
- Paired Android devices provide registration/liveness only in this slice.
- Android has no continuous observation or real enforcement capability.
- Android requests only internet access.
- Real Android enforcement requires a separate architecture decision and release gate.
