import type { CapacitorConfig } from '@capacitor/cli';

// App nativa de Bbeat (Android). El WebView sirve el frontend ya compilado
// (build-native) y habla con la API de producción en bbeat.howl.wtf.
// Ese build se genera con VITE_API_BASE=https://bbeat.howl.wtf, así que las
// llamadas y las URLs de stream/cover son absolutas (no hay backend local).
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
