// Base de la API.
//
// - Web (mismo-origen): vacío → las llamadas usan rutas relativas (`/api/...`)
//   y el navegador resuelve contra el propio host. La PWA en producción no cambia.
// - App nativa (Capacitor): el WebView sirve el frontend desde https://localhost,
//   así que no hay backend en el mismo origen. Se compila con
//   `VITE_API_BASE=https://bbeat.howl.wtf` y todas las llamadas van ahí.
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

/** Antepone API_BASE a una ruta interna `/api/...`. Deja intactas las URLs que ya
 * son absolutas (http/https) o locales del WebView (blob:, data:, capacitor file). */
export function apiUrl(path: string): string {
  if (!path) return path;
  if (/^[a-z]+:\/\//i.test(path) || path.startsWith('blob:') || path.startsWith('data:')) {
    return path;
  }
  return API_BASE + path;
}
