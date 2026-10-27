// Estado de conexión, deducido de los resultados reales de fetch (no de
// navigator.onLine, que en un WebView suele mentir y reportar "online" sin red).
class NetState {
  online = $state(true);
}
export const net = new NetState();

// Señal central de "volvió la red / la app vuelve a primer plano". Las páginas
// se suscriben con onReconnect() para reintentar sus cargas fallidas.
const listeners = new Set<() => void>();
let debounce: ReturnType<typeof setTimeout> | undefined;
let wired = false;

/** Dispara la señal (con debounce) y asume red hasta que un fetch diga lo contrario. */
export function triggerReconnect() {
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    net.online = true;
    for (const fn of [...listeners]) {
      try {
        fn();
      } catch {}
    }
  }, 400);
}

/** Suscribe fn a la señal de reconexión; devuelve la función para desuscribir. */
export function onReconnect(fn: () => void): () => void {
  if (!wired && typeof window !== 'undefined') {
    wired = true;
    window.addEventListener('online', triggerReconnect);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') triggerReconnect();
    });
  }
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Error que lanza api.ts cuando un fetch falla por falta de red. */
export class OfflineError extends Error {
  constructor(message = 'Sin conexión a internet') {
    super(message);
    this.name = 'OfflineError';
  }
}

export function isOfflineError(e: unknown): boolean {
  return e instanceof OfflineError;
}
