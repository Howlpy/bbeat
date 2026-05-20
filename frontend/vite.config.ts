import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import basicSsl from '@vitejs/plugin-basic-ssl';
import { defineConfig } from 'vite';

// Activa HTTPS local con `BBEAT_HTTPS=1 npm run dev`.
// Necesario para que el Media Session API muestre controles en la
// notificación/lockscreen de Android — Chrome lo bloquea en HTTP no-localhost.
const useHttps = process.env.BBEAT_HTTPS === '1' || process.env.BBEAT_HTTPS === 'true';

export default defineConfig({
  plugins: [tailwindcss(), sveltekit(), ...(useHttps ? [basicSsl()] : [])],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8787',
        changeOrigin: true
      }
    }
  }
});
