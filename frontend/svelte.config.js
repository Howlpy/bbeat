import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// Carpeta de salida. Por defecto `build` (la que sirve FastAPI en producción).
// El build de la app nativa usa `BBEAT_BUILD_DIR=build-native` para no pisarla.
const outDir = process.env.BBEAT_BUILD_DIR || 'build';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: outDir,
      assets: outDir,
      fallback: 'index.html',
      precompress: false,
      strict: false
    }),
    alias: {
      $lib: './src/lib'
    },
    serviceWorker: {
      // En la app nativa (Capacitor) no registramos el SW: el shell ya es local
      // y cachearlo solo estorba al actualizar la APK. En web (PWA) sí.
      register: !process.env.BBEAT_NATIVE
    }
  }
};

export default config;
