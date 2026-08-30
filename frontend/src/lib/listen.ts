/**
 * Regla de "canción escuchada": cuenta cuando se ha oído al menos el 70 % de
 * su duración y de seguido.
 *
 * Vive aparte del reproductor porque es la lógica que decide qué acaba en el
 * Wrapped, y así se puede probar sin un <audio> delante.
 *
 * Se acumulan avances de `currentTime`, no tiempo de reloj. Esa elección es la
 * que hace que una pausa NO rompa la continuidad (mientras está pausado no
 * llegan avances) pero un salto sí.
 */
export const PLAY_COUNT_RATIO = 0.7;

export type ListenState = {
  /** Segundos oídos sin saltos desde el último corte. */
  listenedSec: number;
  /** Última posición vista; -1 = hay que recalibrar tras un salto. */
  lastPos: number;
  /** Ya se registró esta escucha (no se cuenta dos veces). */
  counted: boolean;
};

export function newListen(): ListenState {
  return { listenedSec: 0, lastPos: -1, counted: false };
}

/** Un salto rompe el "de seguido": el contador vuelve a cero. */
export function breakContinuity(state: ListenState): void {
  state.listenedSec = 0;
  state.lastPos = -1;
}

/**
 * Registra la posición actual. Devuelve true SOLO en el instante exacto en que
 * la pista pasa a contar como escuchada, para que quien llame haga el POST una
 * vez y nada más.
 */
export function advance(state: ListenState, pos: number, totalSec: number): boolean {
  // Tras un salto (o al empezar), la primera muestra solo fija el origen.
  if (state.lastPos < 0) {
    state.lastPos = pos;
    return false;
  }

  const delta = pos - state.lastPos;
  state.lastPos = pos;

  // Retroceso: es un rebobinado que no nos llegó como evento 'seeking'.
  if (delta < 0) {
    state.listenedSec = 0;
    return false;
  }
  state.listenedSec += delta;

  if (state.counted) return false;
  if (!(totalSec > 0)) return false;
  if (state.listenedSec < totalSec * PLAY_COUNT_RATIO) return false;

  state.counted = true;
  return true;
}
