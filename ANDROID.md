# Bbeat Android app (Capacitor)

A native APK that wraps the SvelteKit frontend. On top of the PWA it adds:

- **Real offline storage**: downloads are written to disk (`@capacitor/filesystem`), not the browser cache.
- **Reliable background and lock-screen playback** (Chromium WebView, native MediaSession, double `<audio>` with preloading).
- **Android Auto**: Bbeat shows up as a music app, exposes the current queue and accepts car/steering wheel controls.
- **Multi-server**: pick the Bbeat server inside the app; several servers can be saved.
- **Back button handling**: back navigates inside the app instead of closing it (`@capacitor/app`).
- **Offline detection** via `@capacitor/network`, and sharing of the Wrapped image via `@capacitor/share`.
- Native icon, splash screen and system bars matching the app design.

## Installing a release

Download `bbeat-X.Y.Z.apk` from the [Releases page](https://github.com/Howlpy/bbeat/releases) and open it on the phone, accepting "install from unknown sources". The app can also check for updates from Settings.

Over adb: `adb install -r bbeat-X.Y.Z.apk`. The `-r` flag reinstalls keeping data (including offline downloads), as long as the APK is signed with the same keystore.

## Building the APK

Requirements: **JDK 21** and the **Android SDK** with `platform-tools`, `platforms;android-36` and `build-tools;36.0.0`, with `ANDROID_HOME` pointing at the SDK. Capacitor 8 downloads Gradle by itself.

```bash
cd frontend
npm install
npm run apk
```

This runs, in order:

1. `build:native`: a SvelteKit build with `BBEAT_NATIVE=1` (no service worker) into `frontend/build-native`, so it does not overwrite `frontend/build`, which FastAPI serves to the web PWA. Optionally, `VITE_API_BASE=https://your-server npm run apk` bakes in a default server; otherwise users choose one in the app.
2. `cap sync android`: copies the bundle and plugins into the Android project.
3. `./gradlew assembleRelease`: builds and **signs** the APK.

Output:

```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

The first build downloads Gradle and dependencies to `~/.gradle` and takes several minutes. Gradle runs without a resident daemon (see `android/gradle.properties`).

## Testing Android Auto with a sideloaded APK

Android Auto hides apps that do not come from Google Play by default. To test a GitHub APK in a real car:

1. Open the Android Auto settings on the phone.
2. Under **About**, tap the version ten times to enable Android Auto developer mode.
3. Open the developer menu and enable **Unknown sources**.
4. Open Bbeat once, start a song, and reconnect Android Auto.

The app exposes the last queue to the car even if the media service starts before the Bbeat UI.

## Signing (keystore)

- Keystore: `frontend/android/app/bbeat-release.jks`, alias `bbeat`.
- Passwords: `frontend/android/app/keystore.properties`.
- **Both are in `.gitignore` and must never be committed.** Keep a **backup outside the repo**: without the keystore you cannot publish updates over the installed app (users would have to uninstall and lose their downloads).

## Bumping the version

Before a build that will be installed over an existing one, raise both values in `frontend/android/app/build.gradle`:

```gradle
versionCode 27         // integer, +1 per release
versionName "2.6.0"    // visible version string
```

## Architecture (what the native app touches)

- `frontend/src/lib/config.ts` and `lib/server.svelte.ts`: runtime API base. Empty on the web (same origin); on native, the selected server (multi-server with favorites, picker on the login screen). `apiUrl()` prepends it in `api.ts`.
- `frontend/src/lib/offline.svelte.ts`: one interface, two backends: IndexedDB (web) and `@capacitor/filesystem` + `convertFileSrc()` (native).
- `frontend/src/lib/player.svelte.ts`: double `<audio>` (active plus a preloaded standby). Auto-advance swaps to the already buffered element instead of a cold `load()`, so it is not throttled with the screen locked. This also improves the web PWA.
- `frontend/src/lib/backstack.svelte.ts` and the root layout: Android back button handling.
- `backend/app/config.py`: CORS always allows `https://localhost` and `capacitor://localhost` (the native WebView origins).

## Native plugins (Capacitor)

- `@capacitor/filesystem`: offline downloads to disk.
- `@capacitor/app`: back button handling.
- `@capacitor/network`: connectivity status for offline mode.
- `@capacitor/share`: share the Wrapped image.
- `BbeatAutoPlugin` and `BbeatAutoService`: native media session, notification, background playback and a browsable catalog for Android Auto. Car events are forwarded to the Svelte player through Capacitor.
- `@capawesome/capacitor-android-edge-to-edge-support`: applies insets to the WebView so content does not overlap system bars. Colors are set in `capacitor.config.ts` under `EdgeToEdge`.
- `@capacitor/local-notifications`: only used to request the `POST_NOTIFICATIONS` permission (Android 13+) at startup.

**Manifest permissions added by hand** in `android/app/src/main/AndroidManifest.xml` include `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK` (Android 14+), `POST_NOTIFICATIONS` (Android 13+) and `REQUEST_INSTALL_PACKAGES` (in-app updates). Without the first three, playback crashes or the notification does not show.

## Icon and splash

Source: `frontend/assets/icon.png` (1024 px, rasterized from the maskable SVG with sharp). Regenerate the Android resources with:

```bash
npx capacitor-assets generate --android --iconBackgroundColor '#0F1626' --iconBackgroundColorDark '#0F1626'
```

Warning: this command **reformats `AndroidManifest.xml`**. After running it, check that the permissions above are still present. The background color above is the value used before the redesign; check it against the current icon assets before regenerating.

## Publishing a release

```bash
gh release create vX.Y.Z bbeat-X.Y.Z.apk --repo <your-user>/bbeat --target main \
  --title "BBeat vX.Y.Z" --notes "..."
```

The APK is not stored in git (it is a binary), only as a release asset. The keystore, `.env` and `data/secrets/` are in `.gitignore` and are never pushed.
