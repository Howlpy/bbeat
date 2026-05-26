// Estado de conexión, deducido de los resultados reales de fetch (no de
// navigator.onLine, que en un WebView suele mentir y reportar "online" sin red).
class NetState {
  online = $state(true);
}
export const net = new NetState();

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
