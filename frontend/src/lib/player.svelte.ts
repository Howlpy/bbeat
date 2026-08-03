import { api, type Track } from './api';
import { offline } from './offline.svelte';
import { media } from './media';

const VOLUME_KEY = "bbeat:volume";
const MUTED_KEY = "bbeat:muted";
const SHUFFLE_KEY = "bbeat:shuffle";
const REPEAT_KEY = "bbeat:repeat";
const PAUSE_SETTLE_MS = 750;

export type RepeatMode = 'off' | 'all' | 'one';


function readPersistedVolume(): number {
  if (typeof localStorage === "undefined") return 1;
  const raw = localStorage.getItem(VOLUME_KEY);
  if (raw === null) return 1;
  const v = parseFloat(raw);
  return isFinite(v) ? Math.max(0, Math.min(1, v)) : 1;
}

function readPersistedMuted(): boolean {
  if (typeof localStorage === "undefined") return false;
  return localStorage.getItem(MUTED_KEY) === "1";
}

function readPersistedShuffle(): boolean {
  if (typeof localStorage === "undefined") return false;
  return localStorage.getItem(SHUFFLE_KEY) === "1";
}

function readPersistedRepeat(): RepeatMode {
  if (typeof localStorage === "undefined") return 'off';
  const v = localStorage.getItem(REPEAT_KEY);
  return v === 'all' || v === 'one' ? v : 'off';
}

/** Fisher-Yates sobre una copia. Si `first` se pasa, queda fijado al principio. */
function shuffled(tracks: Track[], first: Track | null): Track[] {
  const rest = tracks.filter((t) => !first || t.id !== first.id);
  for (let i = rest.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [rest[i], rest[j]] = [rest[j], rest[i]];
  }
  return first ? [first, ...rest] : rest;
}


class PlayerState {
  queue = $state<Track[]>([]);
  index = $state(0);
  isPlaying = $state(false);
  position = $state(0);
  duration = $state(0);
  volume = $state(readPersistedVolume());
  muted = $state(readPersistedMuted());
  shuffle = $state(readPersistedShuffle());
  repeat = $state<RepeatMode>(readPersistedRepeat());

  current = $derived<Track | null>(this.queue[this.index] ?? null);
  effectiveVolume = $derived(this.muted ? 0 : this.volume);

  // Dos elementos <audio>: uno ACTIVO (sonando) y otro EN ESPERA con la
  // siguiente pista ya precargada. Al terminar una pista intercambiamos y
  // reproducimos el que ya está bufferizado, en vez de hacer src+load+play()
  // sobre un elemento en frío — eso último es justo lo que el SO estrangula
  // con la pantalla bloqueada, cortando el auto-avance en móvil.
  private els: HTMLAudioElement[] = [];
  private activeIdx = 0;
  /** id de la pista precargada en el elemento en espera (null = nada). */
  private preloadedId: number | null = null;

  private get el(): HTMLAudioElement | null {
    return this.els[this.activeIdx] ?? null;
  }
  private get standby(): HTMLAudioElement | null {
    return this.els[1 - this.activeIdx] ?? null;
  }

  /** Orden sin barajar de la cola actual (para poder restaurarlo al quitar shuffle). */
  private baseQueue: Track[] = [];
  /** track_id cuya reproducción ya hemos registrado, para no contar dos veces. */
  private playLogged: number | null = null;

  /** Activo durante una transición de pista para suprimir el pause espurio. */
  private switching = false;
  /**
   * `pause` se emite antes de `ended` al finalizar una pista en Chromium.
   * Conservamos la pausa espontánea durante un instante para que `ended`
   * pueda convertirla en auto-avance sin desmontar la sesión nativa.
   */
  private pendingPauseTimer: ReturnType<typeof setTimeout> | null = null;
  /** Elemento cuya pausa procede inequívocamente de un control del usuario/SO. */
  private explicitPauseElement: HTMLAudioElement | null = null;
  /** Heartbeat de 'sonando ahora' mientras hay reproducción. */
  private nowPlayingTimer: ReturnType<typeof setInterval> | null = null;

  private cancelPendingPause() {
    if (this.pendingPauseTimer !== null) {
      clearTimeout(this.pendingPauseTimer);
      this.pendingPauseTimer = null;
    }
  }

  private publishPaused(el: HTMLAudioElement, explicit = false) {
    if (el !== this.el || !el.paused || (this.switching && !explicit)) return;
    this.isPlaying = false;
    this.setPlaybackState('paused');
    this.stopNowPlaying();
  }

  attach(a: HTMLAudioElement, b: HTMLAudioElement) {
    this.els = [a, b];
    for (const el of this.els) {
      el.volume = this.effectiveVolume;
      el.preload = 'auto';

      el.addEventListener('timeupdate', () => {
        if (el !== this.el) return;
        this.position = el.currentTime;
        this.updatePositionState();
      });
      el.addEventListener('loadedmetadata', () => {
        if (el !== this.el) return;
        this.duration = el.duration;
        this.updatePositionState();
      });
      el.addEventListener('ended', () => {
        if (el !== this.el) return;
        this.cancelPendingPause();
        this.explicitPauseElement = null;
        this.next(true);
      });
      el.addEventListener('play', () => {
        if (el !== this.el) return;
        this.cancelPendingPause();
        this.explicitPauseElement = null;
        this.isPlaying = true;
        this.setPlaybackState('playing');
        this.startNowPlaying();
      });
      el.addEventListener('pause', () => {
        if (el !== this.el) return;
        const explicitlyRequested = this.explicitPauseElement === el;
        this.explicitPauseElement = null;

        if (explicitlyRequested) {
          this.cancelPendingPause();
          this.publishPaused(el, true);
          return;
        }

        // load() y el intercambio de elementos emiten pausas que no reflejan
        // el estado final del reproductor.
        if (this.switching) return;

        const canAutoAdvance = this.repeat === 'one' || this.autoNextIndex() !== null;
        if (canAutoAdvance) {
          // No dependas de `el.ended`: Android WebView puede disparar `pause`
          // antes de actualizarlo. `ended` o el siguiente `play` cancelarán
          // esta confirmación; una pausa real espontánea se publica después.
          this.cancelPendingPause();
          this.pendingPauseTimer = setTimeout(() => {
            this.pendingPauseTimer = null;
            this.publishPaused(el);
          }, PAUSE_SETTLE_MS);
          return;
        }

        this.publishPaused(el);
      });
    }

    // Nota: NO reanudamos automáticamente al volver a primer plano. Si el
    // usuario (o el SO) paró la reproducción, se queda parada hasta que se
    // pulse play de nuevo. Antes había un "safety net" en visibilitychange que
    // la reactivaba sola al reabrir la app — comportamiento no deseado.
  }

  /** URL de reproducción de una pista: blob/fichero local si está descargada, si no el stream. */
  private srcFor(t: Track): string {
    return offline.audioUrl(t.id) ?? t.stream_url;
  }

  pauseExplicit() {
    const el = this.el;
    if (!el) return;
    this.cancelPendingPause();
    this.explicitPauseElement = el;
    if (el.paused) {
      this.explicitPauseElement = null;
      this.publishPaused(el, true);
      return;
    }
    el.pause();
  }

  /** Marca 'sonando ahora' la pista actual y mantiene el heartbeat (~25s). */
  private startNowPlaying() {
    const cur = this.current;
    if (!cur) return;
    api.nowPlayingPing(cur.id);
    if (this.nowPlayingTimer) return;
    this.nowPlayingTimer = setInterval(() => {
      const c = this.current;
      if (c && this.isPlaying) api.nowPlayingPing(c.id);
    }, 25_000);
  }

  /** Para el heartbeat y sale del feed en vivo. */
  private stopNowPlaying() {
    if (this.nowPlayingTimer) {
      clearInterval(this.nowPlayingTimer);
      this.nowPlayingTimer = null;
    }
    api.nowPlayingStop();
  }

  playTracks(tracks: Track[], startIndex = 0) {
    this.baseQueue = tracks;
    const start = Math.max(0, Math.min(startIndex, tracks.length - 1));
    if (this.shuffle && tracks.length > 1) {
      this.queue = shuffled(tracks, tracks[start] ?? null);
      this.index = 0;
    } else {
      this.queue = tracks;
      this.index = start;
    }
    this.loadCurrent(true);
  }

  /** Reproduce el set entero barajado (botón "Reproducir aleatorio"). */
  playShuffled(tracks: Track[]) {
    if (!tracks.length) return;
    if (!this.shuffle) {
      this.shuffle = true;
      this.persistShuffle();
    }
    this.baseQueue = tracks;
    this.queue = shuffled(tracks, null);
    this.index = 0;
    this.loadCurrent(true);
  }

  /** Activa/desactiva aleatorio conservando la pista en curso. */
  toggleShuffle() {
    this.shuffle = !this.shuffle;
    this.persistShuffle();
    const cur = this.current;
    const base = this.baseQueue.length ? this.baseQueue : this.queue;
    if (this.shuffle) {
      this.queue = shuffled(base, cur);
      this.index = cur ? 0 : this.index;
    } else {
      this.queue = [...base];
      this.index = cur ? Math.max(0, this.queue.findIndex((t) => t.id === cur.id)) : this.index;
    }
    this.preloadNext();
  }

  private persistShuffle() {
    if (typeof localStorage === "undefined") return;
    try {
      localStorage.setItem(SHUFFLE_KEY, this.shuffle ? "1" : "0");
    } catch {
      // ignorar quota errors
    }
  }

  enqueue(track: Track) {
    this.queue = [...this.queue, track];
    this.preloadNext();
  }

  private loadCurrent(autoplay: boolean) {
    const el = this.el;
    if (!el || !this.current) return;
    this.cancelPendingPause();
    this.explicitPauseElement = null;
    // Marca que estamos cambiando para suprimir el pause espurio del <audio>.
    this.switching = true;
    // Mantén playbackState='playing' en MediaSession durante la transición
    // para que Android NO descarte la notificación.
    this.setPlaybackState('playing');
    // metadata DEBE ir antes del .play() para que el OS enganche la sesión
    this.updateMediaSession();

    el.src = this.srcFor(this.current);
    el.load();

    const cur = this.current;
    const done = () => {
      this.switching = false;
      // Con la pista en marcha, precarga la siguiente en el elemento en espera.
      this.preloadNext();
    };
    if (autoplay) {
      el.play().then(() => {
        done();
        // Registrar la reproducción una sola vez por pista (historial + top).
        if (cur && this.playLogged !== cur.id) {
          this.playLogged = cur.id;
          api.recordPlay(cur.id).catch(() => {});
        }
      }, (err) => {
        console.warn('[bbeat] autoplay rechazado:', err);
        done();
      });
    } else {
      done();
    }
  }

  /** Índice al que saltaría el auto-avance (o null si no hay siguiente). */
  private autoNextIndex(): number | null {
    if (this.index < this.queue.length - 1) return this.index + 1;
    if (this.repeat === 'all' && this.queue.length) return 0;
    return null;
  }

  /** Precarga la siguiente pista en el elemento en espera (sin reproducirla). */
  private preloadNext() {
    const sb = this.standby;
    if (!sb) return;
    // En repeat-one la "siguiente" es la misma que suena: no hace falta espera.
    if (this.repeat === 'one') return;
    const ni = this.autoNextIndex();
    if (ni === null) return;
    const t = this.queue[ni];
    if (!t) return;
    if (this.preloadedId === t.id && sb.src) return; // ya precargada
    sb.src = this.srcFor(t);
    sb.preload = 'auto';
    sb.load();
    this.preloadedId = t.id;
  }

  toggle() {
    const el = this.el;
    if (!el) return;
    if (el.paused) {
      el.play();
    } else {
      this.pauseExplicit();
    }
  }

  next(auto = false) {
    // Repeat-one: al acabar sola, reproduce de nuevo la misma (manual sí avanza).
    if (auto && this.repeat === 'one') {
      this.playLogged = null; // que cuente como nueva reproducción
      this.loadCurrent(true);
      return;
    }
    const ni = this.autoNextIndex();
    if (ni === null) {
      const el = this.el;
      this.cancelPendingPause();
      this.explicitPauseElement = null;
      if (el) {
        el.pause();
        this.publishPaused(el);
      }
      return;
    }
    const target = this.queue[ni];
    const sb = this.standby;
    // Auto-avance con la siguiente ya precargada y lista → intercambia y
    // reproduce el elemento en espera. play() sobre algo bufferizado NO se
    // estrangula con la pantalla bloqueada (a diferencia de un load() en frío).
    if (auto && sb && this.preloadedId === target?.id && sb.readyState >= 2) {
      this.advanceBySwap(ni);
    } else {
      this.index = ni;
      this.loadCurrent(true);
    }
  }

  /** Avanza intercambiando al elemento en espera (precargado). */
  private advanceBySwap(ni: number) {
    const old = this.el;
    const nw = this.standby;
    if (!nw) {
      this.index = ni;
      this.loadCurrent(true);
      return;
    }
    this.cancelPendingPause();
    this.explicitPauseElement = null;
    this.switching = true;
    this.setPlaybackState('playing');
    this.index = ni;
    this.activeIdx = 1 - this.activeIdx; // a partir de aquí this.el === nw
    this.preloadedId = null;
    this.updateMediaSession();

    old?.pause();
    if (old) {
      try { old.currentTime = 0; } catch { /* ignore */ }
    }

    nw.volume = this.effectiveVolume;
    this.duration = isFinite(nw.duration) ? nw.duration : 0;
    this.position = nw.currentTime;
    this.updatePositionState();

    const cur = this.current;
    nw.play().then(() => {
      this.switching = false;
      if (cur && this.playLogged !== cur.id) {
        this.playLogged = cur.id;
        api.recordPlay(cur.id).catch(() => {});
      }
      this.preloadNext(); // ahora precarga la siguiente en el elemento liberado
    }, (err) => {
      console.warn('[bbeat] play tras swap rechazado, recargo en frío:', err);
      this.switching = false;
      this.loadCurrent(true);
    });
  }

  cycleRepeat() {
    this.repeat = this.repeat === 'off' ? 'all' : this.repeat === 'all' ? 'one' : 'off';
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.setItem(REPEAT_KEY, this.repeat);
      } catch {
        // ignorar
      }
    }
    this.preloadNext();
  }

  // ─── Cola ──────────────────────────────────────────────────────
  /** Añade pista(s) al final de la cola. Si no hay nada sonando, arranca. */
  addToQueue(t: Track | Track[]) {
    const arr = Array.isArray(t) ? t : [t];
    if (!arr.length) return;
    const wasEmpty = this.queue.length === 0;
    this.queue = [...this.queue, ...arr];
    this.baseQueue = [...this.baseQueue, ...arr];
    if (wasEmpty) {
      this.index = 0;
      this.loadCurrent(true);
    } else {
      this.preloadNext();
    }
  }

  /** Inserta una pista justo después de la actual. */
  playNext(t: Track) {
    if (!this.queue.length) {
      this.addToQueue(t);
      return;
    }
    const at = this.index + 1;
    this.queue = [...this.queue.slice(0, at), t, ...this.queue.slice(at)];
    this.baseQueue = [...this.baseQueue, t];
    this.preloadNext();
  }

  /** Salta a una posición concreta de la cola. */
  jumpTo(i: number) {
    if (i >= 0 && i < this.queue.length) {
      this.index = i;
      this.loadCurrent(true);
    }
  }

  /** Quita una pista de la cola por índice. */
  removeFromQueue(i: number) {
    if (i < 0 || i >= this.queue.length) return;
    const removingCurrent = i === this.index;
    this.queue = [...this.queue.slice(0, i), ...this.queue.slice(i + 1)];
    if (removingCurrent) {
      if (this.index >= this.queue.length) this.index = Math.max(0, this.queue.length - 1);
      if (this.queue.length) this.loadCurrent(this.isPlaying);
      else {
        this.pauseExplicit();
      }
    } else {
      if (i < this.index) this.index -= 1;
      this.preloadNext();
    }
  }

  /** Marca/desmarca me gusta la pista actual (optimista). */
  toggleLikeCurrent() {
    const t = this.current;
    if (!t) return;
    const next = !t.liked;
    t.liked = next;
    (next ? api.likeTrack(t.id) : api.unlikeTrack(t.id)).catch(() => {
      t.liked = !next;
    });
  }

  prev() {
    const el = this.el;
    if (el && el.currentTime > 3) {
      el.currentTime = 0;
      return;
    }
    if (this.index > 0) {
      this.index -= 1;
      this.loadCurrent(true);
    }
  }

  seek(seconds: number) {
    if (this.el) this.el.currentTime = seconds;
  }

  setVolume(v: number) {
    this.volume = Math.max(0, Math.min(1, v));
    this.muted = false;
    this.persistVolume();
    this.applyVolume();
  }

  toggleMute() {
    this.muted = !this.muted;
    this.persistVolume();
    this.applyVolume();
  }

  private applyVolume() {
    // Aplica a ambos elementos para que el que está en espera arranque al volumen correcto.
    for (const el of this.els) el.volume = this.effectiveVolume;
  }

  private persistVolume() {
    if (typeof localStorage === "undefined") return;
    try {
      localStorage.setItem(VOLUME_KEY, this.volume.toFixed(3));
      localStorage.setItem(MUTED_KEY, this.muted ? "1" : "0");
    } catch {
      // ignorar quota errors
    }
  }

  // ─── Media Session (web navigator + notificación nativa) ──────
  private actionHandlersSet = false;

  private updateMediaSession() {
    if (!media.available) return;
    const t = this.current;
    if (!t) return;

    // URL absoluta obligatoria. Si la pista está descargada, usa la carátula
    // local (sigue visible offline); si no, la remota.
    const local = offline.coverUrl(t.id);
    const artwork = local
      ? [{ src: local, sizes: '512x512', type: 'image/jpeg' }]
      : t.cover_url
        ? [{ src: new URL(t.cover_url, window.location.origin).toString(), sizes: '512x512', type: 'image/jpeg' }]
        : [];

    media.setMetadata({
      title: t.title,
      artist: t.artist_name,
      album: t.album_title ?? '',
      artwork
    });
    media.setQueue(
      this.queue.map((item) => ({
        id: item.id,
        title: item.title,
        artist: item.artist_name,
        album: item.album_title ?? '',
        artwork: item.cover_url
          ? [{ src: new URL(item.cover_url, window.location.origin).toString(), sizes: '512x512', type: 'image/jpeg' }]
          : []
      })),
      this.index
    );

    // Los handlers no dependen de la pista; basta registrarlos una vez.
    if (this.actionHandlersSet) return;
    this.actionHandlersSet = true;
    media.setActionHandler('play', () => this.el?.play());
    media.setActionHandler('pause', () => this.pauseExplicit());
    media.setActionHandler('stop', () => this.pauseExplicit());
    media.setActionHandler('nexttrack', () => this.next());
    media.setActionHandler('previoustrack', () => this.prev());
    media.setActionHandler('seekbackward', () => this.seek(Math.max(0, (this.el?.currentTime ?? 0) - 10)));
    media.setActionHandler('seekforward', () =>
      this.seek(Math.min(this.el?.duration ?? 0, (this.el?.currentTime ?? 0) + 10))
    );
    media.setActionHandler('seekto', (d) => {
      if (d.seekTime != null) this.seek(d.seekTime);
    });
    media.setActionHandler('playfrommediaid', (d) => {
      if (d.index != null) this.jumpTo(d.index);
    });
  }

  private setPlaybackState(state: 'none' | 'paused' | 'playing') {
    media.setPlaybackState(state);
  }

  private updatePositionState() {
    const el = this.el;
    if (!el || !isFinite(el.duration) || el.duration <= 0) return;
    media.setPositionState({
      duration: el.duration,
      position: el.currentTime,
      playbackRate: el.playbackRate || 1.0
    });
  }
}

export const player = new PlayerState();
