import type { CapacitorConfig } from '@capacitor/cli';

// App nativa de Bbeat (Android). El WebView sirve el frontend ya compilado
// (build-native) y habla con un servidor bbeat por HTTP. El usuario elige el
// servidor dentro de la app (multi-servidor); opcionalmente se puede hornear
// uno por defecto con VITE_API_BASE al compilar. Las URLs de stream/cover se
// resuelven absolutas en runtime (no hay backend en el mismo origen).
const config: CapacitorConfig = {
  appId: 'wtf.howl.bbeat',
  appName: 'Bbeat',
  webDir: 'build-native',
  android: {
    // El WebView arranca con esquema https://localhost (origen permitido por CORS).
    allowMixedContent: false
  },
  plugins: {
    // edge-to-edge-support mete los insets al WebView (el contenido deja de
    // dibujarse bajo la barra de estado y la de gestos). Pintamos esas zonas
    // del color de fondo de la app (slate-950) para que se integren.
    EdgeToEdge: {
      statusBarColor: '#020617',
      navigationBarColor: '#020617'
    }
  }
};

export default config;
