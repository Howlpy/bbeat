# Bbeat — app nativa de Android (Capacitor)

APK nativa que envuelve el frontend SvelteKit. Añade sobre la PWA:

- **Offline real**: descargas a fichero en disco (`@capacitor/filesystem`), no caché del navegador.
- **Reproducción en segundo plano / pantalla bloqueada** fiable (WebView Chromium + MediaSession nativo + doble `<audio>` con precarga).
- Llama a la API de producción `https://bbeat.howl.wtf`.

## Cómo se compila

Toolchain ya instalado en este host: Android SDK en `~/Android/Sdk` (platform-tools, `android-36`, build-tools 36), JDK 21. `ANDROID_HOME` exportado en `~/.bashrc`.

```bash
cd frontend
npm run apk
```

Eso hace, en orden:
1. `build:native` — build de SvelteKit con `VITE_API_BASE=https://bbeat.howl.wtf`, `BBEAT_NATIVE=1` (sin service worker) → carpeta `frontend/build-native` (no pisa `frontend/build`, que sirve FastAPI a la PWA web).
2. `cap sync android` — copia el bundle y los plugins al proyecto Android.
3. `./gradlew assembleRelease` — compila y **firma** la APK.

APK firmada resultante:

```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

(El primer build descarga Gradle + dependencias a `~/.gradle`, tarda varios minutos. Gradle corre sin daemon residente para no molestar a bbeat/bots — ver `android/gradle.properties`.)

## Instalar en el móvil

- **Por cable (adb)**: `~/Android/Sdk/platform-tools/adb install -r .../app-release.apk`
- **Sin cable**: copia el `.apk` al teléfono (Telegram, nube, `python -m http.server`…) y ábrelo; acepta "instalar de orígenes desconocidos".

El `-r` reinstala conservando datos (descargas offline incluidas), siempre que esté firmada con el mismo keystore.

## Firma (keystore) — IMPORTANTE

- Keystore: `frontend/android/app/bbeat-release.jks`, alias `bbeat`.
- Contraseñas: `frontend/android/app/keystore.properties`.
- **Ambos están en `.gitignore` — NO se commitean.** Haz una **copia de seguridad fuera del repo**: si pierdes el keystore no podrás publicar actualizaciones sobre la app instalada (habría que desinstalar y perder las descargas).

## Subir de versión

Antes de un build nuevo que vayas a instalar encima, sube en `frontend/android/app/build.gradle`:

```gradle
versionCode 2          // entero, +1 cada release
versionName "1.1"      // string visible
```

## Arquitectura (qué tocó la app nativa)

- `frontend/src/lib/config.ts` — `API_BASE` (vacío en web → relativo; absoluto en nativo). `apiUrl()` la antepone en `api.ts` (`json()` y `tokenizeUrls()`).
- `frontend/src/lib/offline.svelte.ts` — misma interfaz, dos backends: IndexedDB (web) y `@capacitor/filesystem` + `convertFileSrc()` (nativo).
- `frontend/src/lib/player.svelte.ts` — doble `<audio>` (activo + en espera precargado). El auto-avance intercambia al elemento ya bufferizado en vez de `load()` en frío → no se estrangula con la pantalla bloqueada. **Esto mejora también la PWA web.**
- `backend/app/config.py` — CORS permite siempre `https://localhost` / `capacitor://localhost` (orígenes del WebView nativo).

## Si el segundo plano fallara en algún dispositivo (plan B)

La hipótesis es que el WebView de la app (a diferencia de una pestaña de navegador) sigue reproduciendo bloqueado. Si en tu móvil concreto Android mata el audio al bloquear:

1. Añadir un *foreground service* nativo (notificación persistente mientras suena) en el proyecto Android, arrancado al empezar a reproducir.
2. Declarar `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_MEDIA_PLAYBACK` en el manifest.

No se incluye de inicio para no meter dependencias frágiles; se añade si las pruebas en dispositivo lo piden.
