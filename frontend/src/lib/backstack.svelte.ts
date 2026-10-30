// Pila de "cierres" para el botón/gesto atrás de Android: los overlays
// (player, cola, menús, diálogos) registran su cierre al abrirse y lo quitan
// al cerrarse; el atrás cierra el de arriba antes de navegar.
import { goto } from '$app/navigation';
import type { AfterNavigate } from '@sveltejs/kit';

const stack: Array<() => void> = [];

/** Registra un cierre. Devuelve la función para desregistrarlo. */
export function pushBack(close: () => void): () => void {
  stack.push(close);
  return () => {
    const i = stack.lastIndexOf(close);
    if (i >= 0) stack.splice(i, 1);
  };
}

/** Cierra el overlay superior. Devuelve true si había alguno. */
export function popBack(): boolean {
  const close = stack.pop();
  if (!close) return false;
  try {
    close();
  } catch {
    /* un cierre roto no debe bloquear el atrás */
  }
  return true;
}

// Navegaciones internas apiladas (no se fía de window.history.length).
let depth = $state(0);

export const nav = {
  get hasHistory() {
    return depth > 0;
  }
};

/** Llamar desde afterNavigate del layout. */
export function trackNav(n: AfterNavigate) {
  if (n.type === 'enter') depth = 0;
  else if (n.type === 'popstate') depth = Math.max(0, depth + (n.delta ?? -1));
  else if (n.type === 'link' || n.type === 'goto') depth += 1;
}

/** Vuelve atrás si hay historial interno; si no, va al `fallback`. */
export function goBack(fallback = '/') {
  if (depth > 0) history.back();
  else goto(fallback);
}
