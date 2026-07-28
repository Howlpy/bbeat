# Bbeat — app nativa de Android (Capacitor)

APK nativa que envuelve el frontend SvelteKit. Añade sobre la PWA:

- **Offline real**: descargas a fichero en disco (`@capacitor/filesystem`), no caché del navegador.
- **Reproducción en segundo plano / pantalla bloqueada** fiable (WebView Chromium + MediaSession nativo + doble `<audio>` con precarga).
- **Android Auto**: BBeat aparece como app de música, expone la cola actual y acepta los controles del coche/volante.
- **Multi-servidor**: te conectas al servidor bbeat que elijas dentro de la app (con favoritos guardados).

## Cómo se compila

Requisitos: **JDK 21** y **Android SDK** con `platform-tools`, `platforms;android-36` y `build-tools;36.0.0`, con `ANDROID_HOME` apuntando al SDK. Capacitor 8 descarga Gradle por su cuenta.

```bash
cd frontend
npm run apk
```

Eso hace, en orden:
1. `build:native` — build de SvelteKit con `BBEAT_NATIVE=1` (sin service worker) → carpeta `frontend/build-native` (no pisa `frontend/build`, que sirve FastAPI a la PWA web). Opcional: `VITE_API_BASE=https://tu-servidor npm run apk` hornea un servidor por defecto; si no, el usuario lo elige en la app al entrar.
2. `cap sync android` — copia el bundle y los plugins al proyecto Android.
3. `./gradlew assembleRelease` — compila y **firma** la APK.

APK firmada resultante:

```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

(El primer build descarga Gradle + dependencias a `~/.gradle`, tarda varios minutos. Gradle corre sin daemon residente — ver `android/gradle.properties`.)

## Instalar en el móvil

- **Por cable (adb)**: `~/Android/Sdk/platform-tools/adb install -r .../app-release.apk`
- **Sin cable**: copia el `.apk` al teléfono (Telegram, nube, `python -m http.server`…) y ábrelo; acepta "instalar de orígenes desconocidos".

El `-r` reinstala conservando datos (descargas offline incluidas), siempre que esté firmada con el mismo keystore.

## Probar Android Auto con una APK instalada a mano

Android Auto oculta por defecto las apps que no proceden de Google Play. Para
probar una APK de GitHub en un coche real:

1. Abre los ajustes de Android Auto en el móvil.
2. En **Información/Acerca de**, pulsa diez veces sobre la versión para activar
   el modo desarrollador de Android Auto.
3. Abre el menú de desarrollador y activa **Fuentes desconocidas**.
4. Abre BBeat una vez, inicia una canción y vuelve a conectar Android Auto.

La app expone la última cola al coche incluso si el servicio multimedia se
inicia antes que la interfaz de BBeat.

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

- `frontend/src/lib/config.ts` + `lib/server.svelte.ts` — base de la API en runtime: vacía en web (mismo origen); en nativo, el servidor elegido (multi-servidor con favoritos, selector en el login). `apiUrl()` la antepone en `api.ts`.
- `frontend/src/lib/offline.svelte.ts` — misma interfaz, dos backends: IndexedDB (web) y `@capacitor/filesystem` + `convertFileSrc()` (nativo).
- `frontend/src/lib/player.svelte.ts` — doble `<audio>` (activo + en espera precargado). El auto-avance intercambia al elemento ya bufferizado en vez de `load()` en frío → no se estrangula con la pantalla bloqueada. **Esto mejora también la PWA web.**
- `backend/app/config.py` — CORS permite siempre `https://localhost` / `capacitor://localhost` (orígenes del WebView nativo).

## Plugins nativos (Capacitor)

- `@capacitor/filesystem` — descargas offline a disco.
- `BbeatAutoPlugin` + `BbeatAutoService` — sesión multimedia nativa, notificación, reproducción en segundo plano y catálogo navegable para Android Auto. Los eventos del coche se envían al reproductor Svelte mediante Capacitor.
- `@capawesome/capacitor-android-edge-to-edge-support` — mete los insets al WebView (no se solapa con barras de estado/gestos). Colores en `capacitor.config.ts` → `EdgeToEdge`.
- `@capacitor/local-notifications` — solo para pedir el permiso `POST_NOTIFICATIONS` (Android 13+) al arrancar.

**Permisos añadidos a mano** en `android/app/src/main/AndroidManifest.xml`: `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MEDIA_PLAYBACK` (Android 14+) y `POST_NOTIFICATIONS` (Android 13+). Sin ellos, peta al reproducir o no se ve la notificación.

## Icono / splash

Fuente: `frontend/assets/icon.png` (1024, rasterizado del SVG maskable con sharp). Regenerar los recursos Android:

```bash
npx capacitor-assets generate --android --iconBackgroundColor '#0F1626' --iconBackgroundColorDark '#0F1626'
```

⚠️ Ese comando **reformatea `AndroidManifest.xml`**: tras correrlo, comprueba que siguen los dos permisos de arriba.

## Publicar una release

```bash
gh release create vX.Y ~/bbeat-vX.Y.apk --repo <tu-usuario>/bbeat --target main \
  --title "Bbeat Android vX.Y" --notes "..."
```

La APK no va dentro del árbol de git (es binario), solo como asset de release. El keystore, `.env` y `data/secrets/` están en `.gitignore` — nunca se suben.
