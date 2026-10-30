import { apiUrl } from './config';

// Estado de conexión: ÚNICA fuente de verdad (net.online). Se alimenta de:
//  - el SO (nativo: @capacitor/network; web: eventos online/offline),
//  - los resultados reales de fetch (api.ts → markOnline/markOffline),
//  - un sondeo a /api/health mientras estamos offline para detectar la vuelta.
// navigator.onLine por sí solo miente en un WebView, de ahí el sondeo.
class NetState {
  online = $state(true);
}
export const net = new NetState();

const PROBE_EVERY_MS = 10_000;
const PROBE_TIMEOUT_MS = 4_000;
const RELOAD_AFTER_HIDDEN_MS = 60_000;

const listeners = new Set<() => void>(); // reconexión (recargar datos)
const statusListeners = new Set<(online: boolean) => void>(); // cualquier cambio
let debounce: ReturnType<typeof setTimeout> | undefined;
let probeTimer: ReturnType<typeof setInterval> | undefined;
let probing: Promise<boolean> | null = null;
let started = false;

function fire() {
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    for (const fn of [...listeners]) {
      try {
        fn();
      } catch {}
    }
  }, 400);
}

function setOnline(v: boolean) {
  if (net.online === v) return;
  net.online = v;
  for (const fn of [...statusListeners]) {
    try {
      fn(v);
    } catch {}
  }
}

/** Hay respuesta del servidor → hay red. Si veníamos de offline, avisa a las páginas. */
export function markOnline() {
  stopProbing();
  if (!net.online) {
    setOnline(true);
    fire();
  }
}

/** Falló la red (fetch/audio/SO): pasa a offline al instante y empieza a sondear. */
export function markOffline() {
  setOnline(false);
  startProbing();
}

/** Pide un GET barato al backend. Actualiza net.online según el resultado. */
export function probe(): Promise<boolean> {
  if (typeof window === 'undefined') return Promise.resolve(true);
  if (probing) return probing;
  probing = (async () => {
    // Online: exige 2 sondeos fallidos seguidos antes de dar la red por caída
    // (un timeout suelto en una red lenta no significa "sin internet").
    const attempts = net.online ? 2 : 1;
    for (let i = 0; i < attempts; i++) {
      if (i > 0) await new Promise((r) => setTimeout(r, 1_000));
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
      try {
        // Cualquier respuesta HTTP (incluso 5xx) = hay red; un error del servidor no es "sin internet".
        await fetch(apiUrl('/api/health'), { cache: 'no-store', signal: ctrl.signal });
        markOnline();
        return true;
      } catch {
        // sin red / timeout
      } finally {
        clearTimeout(timer);
      }
    }
    markOffline();
    return false;
  })().finally(() => {
    probing = null;
  });
  return probing;
}

function startProbing() {
  if (probeTimer || typeof document === 'undefined' || document.visibilityState === 'hidden') return;
  probeTimer = setInterval(() => {
    if (net.online || document.visibilityState === 'hidden') return stopProbing();
    probe();
  }, PROBE_EVERY_MS);
}

function stopProbing() {
  clearInterval(probeTimer);
  probeTimer = undefined;
}

/** Señal de "volvió la red / la app vuelve a primer plano". Si estábamos offline
 * comprueba primero que de verdad hay servidor; si no, recarga las páginas ya. */
export function triggerReconnect() {
  if (net.online) fire();
  else probe(); // si responde, markOnline() dispara fire()
}

/** Suscribe fn a la señal de reconexión; devuelve la función para desuscribir. */
export function onReconnect(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Suscribe fn a los cambios de online/offline; devuelve la función para desuscribir. */
export function onNetChange(fn: (online: boolean) => void): () => void {
  statusListeners.add(fn);
  return () => statusListeners.delete(fn);
}

/** Arranca la detección de red (idempotente). Llamar una vez desde el layout. */
export async function initNet() {
  if (started || typeof window === 'undefined') return;
  started = true;

  let hiddenAt = 0;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      const wasOffline = !net.online;
      const longAway = hiddenAt > 0 && Date.now() - hiddenAt > RELOAD_AFTER_HIDDEN_MS;
      hiddenAt = 0;
      if (wasOffline) startProbing();
      // Recarga solo si estábamos offline o llevaba mucho en segundo plano (evita parpadeos).
      if (wasOffline || longAway) triggerReconnect();
    } else {
      hiddenAt = Date.now();
      stopProbing();
    }
  });

  const { Capacitor } = await import('@capacitor/core');
  if (Capacitor.isNativePlatform()) {
    try {
      const { Network } = await import('@capacitor/network');
      const st = await Network.getStatus();
      if (!st.connected) markOffline();
      await Network.addListener('networkStatusChange', (s) => {
        if (s.connected) triggerReconnect();
        else markOffline();
      });
      return;
    } catch {
      // si el plugin falla, caemos a los eventos del WebView
    }
  }
  window.addEventListener('online', triggerReconnect);
  window.addEventListener('offline', markOffline);
  if (!navigator.onLine) markOffline();
}

/** Mensaje por defecto de OfflineError (las páginas lo reconocen para mostrar el vacío offline). */
export const OFFLINE_MESSAGE = 'Sin conexión a internet';

/** Error que lanza api.ts cuando un fetch falla por falta de red. */
export class OfflineError extends Error {
  constructor(message = OFFLINE_MESSAGE) {
    super(message);
    this.name = 'OfflineError';
  }
}

export function isOfflineError(e: unknown): boolean {
  return e instanceof OfflineError;
}
