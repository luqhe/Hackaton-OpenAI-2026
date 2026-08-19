# Guardian Android

Native Android interface for the Guardian hackathon MVP.

## Stack

- Kotlin 2.3.21
- Jetpack Compose + Material 3
- Android Gradle Plugin 8.13.2
- compileSdk / targetSdk 36
- minSdk 26
- Java 17
- Existing FastAPI Guardian backend as the source of truth for risk, policy, incidents, evidence and device commands

The app intentionally avoids a WebView and does not duplicate the Python risk/policy engine in Kotlin.

## Run the demo

Start the existing Guardian API on the development machine:

```bash
bash scripts/run-api.sh
```

For the Android Emulator, the app defaults to:

```text
http://10.0.2.2:8000
```

For a physical Android device, open **Conexão** in the app and enter an API URL reachable from the phone, such as an HTTPS development endpoint or the machine's LAN address while both devices are on the same trusted network.

Build with Android Studio or with Gradle 8.13:

```bash
gradle :android-app:assembleDebug
```

Then run a controlled fixture from the backend as before:

```bash
bash scripts/run-demo.sh
```

The Android dashboard will show the resulting incident and can execute the existing parent decision endpoints.

## Mobile flows

- Parent dashboard with daily metrics and incident activity.
- Incident detail with evidence summary and unlock / keep-blocked decisions.
- Child transparency view with daily app-use aggregation.
- Family policy editor for ALLOW / ALERT / BLOCK actions.
- API connection configuration.
- Android device pairing through `POST /api/devices/pair`.
- Capability display so the UI does not imply functionality the server has not enabled.

## Permissions and enforcement

This port requests only `INTERNET`. It does **not** request Accessibility, MediaProjection/screen capture, microphone, camera, device-admin or notification-listener permissions.

That is deliberate. The original Guardian MVP is simulation-first and the Android port keeps the same safety boundary. Real Android enforcement should be implemented only after choosing a legitimate device-management model, defining an allowlist/denylist, adding explicit consent and release gates, and updating the threat/privacy model.

Debug builds permit cleartext HTTP so the emulator can reach the local FastAPI demo. Production deployments should use HTTPS and disable cleartext traffic.

## Repository split

The intended `Hackaton-OpenAI-2026-mobile` repository should contain the shared Python backend plus this `android-app/` module. The browser UI may remain as a backend debug/admin interface, but the product-facing mobile experience lives in Compose.
