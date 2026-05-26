import { server } from './server.svelte';

// Base de la API, resuelta EN RUNTIME desde el servidor seleccionado:
// - Web (mismo origen): vacía → rutas relativas (`/api/...`). La PWA no cambia.
// - App nativa (Capacitor): el servidor bbeat elegido por el usuario (multi-servidor).
//   El servidor por defecto se hornea con VITE_API_BASE y queda como favorito semilla.

/** Antepone la base del servidor a una ruta interna `/api/...`. Deja intactas las
 * URLs ya absolutas (http/https) o locales del WebView (blob:, data:, capacitor file). */
export function apiUrl(path: string): string {
  if (!path) return path;
  if (/^[a-z]+:\/\//i.test(path) || path.startsWith('blob:') || path.startsWith('data:')) {
    return path;
  }
  return server.base + path;
}
