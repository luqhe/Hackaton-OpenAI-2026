# Android mobile demo runbook — R2 secure Family model

This runbook is the presentation path for `agent/android-mobile-port` after synchronization with the R2 Family/Device security model.

The Android application is the **Family review client**. The synthetic host fixture uses `device-demo`. Android does not become the protected Device and does not receive a Device credential.

## Demo security model

The demo is intentionally explicit and local-only:

```text
GUARDIAN_DEMO_MODE=true on API
              +
X-Guardian-Demo: true from Android/fixture client
              +
local transport only
              ↓
synthetic family-demo / child-demo / device-demo scope
```

The backend rejects this demo scope outside development/test and rejects it over non-local transport.

For Android, use ADB reverse instead of exposing the demo server to the LAN.

---

## Before the rehearsal

At the repository root:

```bash
git switch agent/android-mobile-port
git pull
bash scripts/bootstrap.sh
```

Optional quality gate:

```bash
.venv/bin/python scripts/run_r3_evals.py --check
```

Stop old Guardian processes, then reset local state:

```bash
bash scripts/reset-demo.sh
```

On Windows use the corresponding `.ps1` bootstrap/reset scripts.

Prepare:

- Android Emulator or USB-connected Android device;
- JDK 17;
- Android SDK 36;
- Gradle 8.13 or Android Studio;
- `adb` available on the host.

No OpenAI key is required for the recommended deterministic demo.

---

# Recommended deterministic demo

## 1. Start the secure demo API

Terminal 1 — macOS/Linux:

```bash
bash scripts/run-mobile-demo-api.sh
```

Windows:

```powershell
.\scripts\run-mobile-demo-api.ps1
```

This launcher sets:

```text
GUARDIAN_ENVIRONMENT=development
GUARDIAN_DEMO_MODE=true
GUARDIAN_API_URL=http://127.0.0.1:8000
```

and binds FastAPI to host loopback only.

Verify on the host:

```text
http://127.0.0.1:8000/api/health
```

## 2. Reverse Android port 8000 to the host

With the emulator/device connected:

```bash
adb reverse tcp:8000 tcp:8000
```

The Android client now reaches host FastAPI by using its own:

```text
http://127.0.0.1:8000
```

This is important. Do not use LAN binding for the synthetic demo; the R2 backend deliberately restricts demo identity to local transport.

## 3. Build/run Android

Android Studio is recommended. Alternatively:

```bash
gradle :android-app:assembleDebug
adb install -r android-app/build/outputs/apk/debug/android-app-debug.apk
```

## 4. Configure Android demo scope

Open **Configuração** and set:

```text
API URL: http://127.0.0.1:8000
Modo de demonstração local: ON
Child ID: child-demo
```

If necessary tap **Usar Device demo**.

The app validates demo scope through `/api/auth/session`. When accepted, it operates inside synthetic `family-demo` without a password.

Do not enter real credentials in demo mode.

## 5. Trigger the controlled fixture

Terminal 2 — macOS/Linux:

```bash
bash scripts/run-mobile-demo.sh
```

Windows:

```powershell
.\scripts\run-mobile-demo.ps1
```

The launcher sets the same explicit demo environment. The host HTTP client reads `GUARDIAN_DEMO_MODE` and adds `X-Guardian-Demo: true` only to legacy synthetic demo requests.

Expected stages:

1. `fixtures/dangerous_contact/session.json` is loaded.
2. Contextual risk is evaluated.
3. Family policy is evaluated separately from classification.
4. Runtime release gates are applied.
5. `device-demo` receives simulated enforcement state.
6. An incident is persisted in `family-demo` with minimal evidence.
7. The host waits for the family decision.

Useful terminal output:

```text
assessment=...
decision=...
incident=...
parent_view=...
child_view=...
```

## 6. Review on Android

In the Android app:

1. open **Início**;
2. tap **Atualizar** if necessary;
3. open the new incident;
4. review category, confidence, application, evidence summary and Device ID;
5. choose **Desbloquear aplicativo** or **Manter bloqueado**.

Android sends family mutations in explicit demo scope. The server keeps that authorization restricted to the local synthetic environment.

On unlock, Terminal 2 should eventually print:

```text
unlocked=Guardian Demo Chat command=<id>
```

That demonstrates the complete mobile vertical slice:

```text
controlled fixture
      ↓
shared risk + policy pipeline
      ↓
Family-scoped incident
      ↓
Android family review
      ↓
persistent unlock command
      ↓
host demo-agent acknowledgement
```

## 7. End the demo

Turn **Modo de demonstração local** off in Android.

Stop the API, then reset before another clean rehearsal:

```bash
bash scripts/reset-demo.sh
```

---

# Normal authenticated Android flow

This is separate from the synthetic demo.

Prerequisites:

- reachable Guardian API;
- HTTPS outside loopback development;
- an existing Account;
- an active Membership in the intended Family;
- a Child ID inside that Family.

Android steps:

1. open **Configuração**;
2. ensure demo mode is OFF;
3. configure the API URL;
4. open **Entrar**;
5. enter Account email/password;
6. provide `family_id` if the Account has more than one active Family Membership;
7. configure the intended Child ID.

The server returns `guardian_session` and `guardian_csrf`. Android keeps both in memory and sends the CSRF value on mutations. Process restart requires login again.

A `401` clears the local in-memory session.

---

# Protected Device pairing from Android

Android is the Family client, not the Device.

From an authenticated Family session:

1. choose **Criar código de pareamento**;
2. Android calls `POST /api/pairing/challenges` for the selected Child;
3. Android displays the short code and expiry;
4. the protected Device generates its own key material;
5. the Device submits the challenge/code + public key to `POST /api/device/pair`;
6. the backend issues a Device credential;
7. the Device stores that credential and uses signed `/api/agent/*` requests.

The Android Family app never receives or stores the protected Device secret.

Do not describe the pairing-code action as “pair this Android”. It creates authorization for another protected endpoint to enroll.

---

# Optional host-side visual demo

The shared branch still supports richer macOS-host observation/classification. Android can remain the Family review UI.

For the optional controlled visual path, follow the shared host documentation and keep provider credentials on the host. If that path creates an incident in the same Family/Child scope, refresh Android and review it normally.

This does not grant Android screen-capture or enforcement capability.

---

# Failure recovery

## Android reports unauthorized

For the synthetic demo confirm all three conditions:

1. API was started with `scripts/run-mobile-demo-api.*`;
2. Android local demo mode is ON;
3. `adb reverse tcp:8000 tcp:8000` is active and API URL is `http://127.0.0.1:8000`.

Do not work around a demo `401` by opening the API to the LAN or disabling authentication.

For normal mode, log in again and verify the Account has an active Membership in the intended Family.

## Fixture launcher receives 401/403

Use `scripts/run-mobile-demo.*`, not the generic launcher, so `GUARDIAN_DEMO_MODE=true` is explicit in the agent process.

## No incident appears

- verify `Child ID = child-demo` during demo;
- select `device-demo` if necessary;
- tap **Atualizar**;
- stop/reset the API if stale demo state caused deduplication.

## ADB reverse is missing

List forwarding state:

```bash
adb reverse --list
```

Recreate it:

```bash
adb reverse tcp:8000 tcp:8000
```

## Port 8000 is busy

Stop the old local API. Do not switch the synthetic demo to a public/LAN host merely to avoid the collision.

---

# Presentation boundaries

State these accurately during the demo:

- Android is a native Family client, not a WebView.
- Android authenticates Family/Membership scope in normal mode.
- Demo identity is explicit, synthetic, local-only and disabled in staging/production.
- The Android app does not hold protected Device credentials.
- The protected Device protocol uses separate signed credentials and replay protection.
- Risk/classifier logic and provider credentials stay on the shared backend/host.
- Android requests only internet permission.
- Android currently performs no continuous observation and no real enforcement.
- Evidence, audit, rate limits and data lifecycle are shared backend controls inherited from `main`.
