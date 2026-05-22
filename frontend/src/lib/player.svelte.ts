import { api, type Track } from './api';
import { offline } from './offline.svelte';

const VOLUME_KEY = "bbeat:volume";
const MUTED_KEY = "bbeat:muted";
const SHUFFLE_KEY = "bbeat:shuffle";
const REPEAT_KEY = "bbeat:repeat";

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

  audio: HTMLAudioElement | null = null;

  /** Orden sin barajar de la cola actual (para poder restaurarlo al quitar shuffle). */
  private baseQueue: Track[] = [];
  /** track_id cuya reproducción ya hemos registrado, para no contar dos veces. */
  private playLogged: number | null = null;

  /** Recuerda si el usuario tenía la pista en play cuando la pestaña pasa a background. */
  private wantsPlay = false;
  /** Activo durante una transición de pista para suprimir el pause espurio. */
  private switching = false;

  attach(el: HTMLAudioElement) {
    this.audio = el;
    el.volume = this.effectiveVolume;

    el.addEventListener('timeupdate', () => {
      this.position = el.currentTime;
      this.updatePositionState();
    });
    el.addEventListener('loadedmetadata', () => {
      this.duration = el.duration;
      this.updatePositionState();
    });
    el.addEventListener('ended', () => this.next(true));
    el.addEventListener('play', () => {
      this.isPlaying = true;
      this.wantsPlay = true;
      this.setPlaybackState('playing');
    });
    el.addEventListener('pause', () => {
      // Cuando estamos cambiando de pista, el <audio> emite pause espurio
      // entre el load() y el nuevo play(). Si lo dejamos pasar, Android
      // ve playbackState='paused' un instante y descarta la notificación.
      if (this.switching) return;
      this.isPlaying = false;
      this.setPlaybackState('paused');
    });

    // Safety net: si Chrome pausa el audio al cambiar de pestaña/app
    // y luego volvemos, reanudar si el usuario estaba reproduciendo.
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (
          document.visibilityState === 'visible' &&
          this.wantsPlay &&
          this.audio &&
          this.audio.paused
        ) {
          this.audio.play().catch(() => {});
        }
      });
    }
  }

  pauseExplicit() {
    this.wantsPlay = false;
    this.audio?.pause();
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
  }

  private loadCurrent(autoplay: boolean) {
    if (!this.audio || !this.current) return;
    // Marca que estamos cambiando para suprimir el pause espurio del <audio>.
    this.switching = true;
    // Mantén playbackState='playing' en MediaSession durante la transición
    // para que Android NO descarte la notificación.
    this.setPlaybackState('playing');
    // metadata DEBE ir antes del .play() para que el OS enganche la sesión
    this.updateMediaSession();

    // Si la pista está descargada, reproduce desde el blob local (offline).
    this.audio.src = offline.audioUrl(this.current.id) ?? this.current.stream_url;
    this.audio.load();

    const cur = this.current;
    const done = () => {
      this.switching = false;
    };
    if (autoplay) {
      this.audio.play().then(() => {
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

  toggle() {
    if (!this.audio) return;
    if (this.audio.paused) {
      this.wantsPlay = true;
      this.audio.play();
    } else {
      this.wantsPlay = false;
      this.audio.pause();
    }
  }

  next(auto = false) {
    // Repeat-one: al acabar sola, reproduce de nuevo la misma (manual sí avanza).
    if (auto && this.repeat === 'one') {
      this.playLogged = null; // que cuente como nueva reproducción
      this.loadCurrent(true);
      return;
    }
    if (this.index < this.queue.length - 1) {
      this.index += 1;
      this.loadCurrent(true);
    } else if (this.repeat === 'all' && this.queue.length) {
      this.index = 0;
      this.loadCurrent(true);
    } else {
      this.audio?.pause();
      this.isPlaying = false;
    }
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
        this.audio?.pause();
        this.isPlaying = false;
      }
    } else if (i < this.index) {
      this.index -= 1;
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
    if (this.audio && this.audio.currentTime > 3) {
      this.audio.currentTime = 0;
      return;
    }
    if (this.index > 0) {
      this.index -= 1;
      this.loadCurrent(true);
    }
  }

  seek(seconds: number) {
    if (this.audio) this.audio.currentTime = seconds;
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
    if (this.audio) this.audio.volume = this.effectiveVolume;
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

  // ─── Media Session API ────────────────────────────────────────
  private hasMediaSession(): boolean {
    return typeof navigator !== 'undefined' && 'mediaSession' in navigator;
  }

  private updateMediaSession() {
    if (!this.hasMediaSession()) {
      console.warn('[bbeat] navigator.mediaSession NO disponible en este navegador');
      return;
    }
    const t = this.current;
    if (!t) {
      navigator.mediaSession.metadata = null;
      return;
    }

    // URL absoluta obligatoria — Chrome ignora rutas relativas
    const artwork = t.cover_url
      ? [
          {
            src: new URL(t.cover_url, window.location.origin).toString(),
            sizes: '512x512',
            type: 'image/jpeg'
          }
        ]
      : [];

    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title,
      artist: t.artist_name,
      album: t.album_title ?? '',
      artwork
    });

    console.log('[bbeat] MediaSession metadata set:', {
      title: t.title,
      artist: t.artist_name,
      album: t.album_title,
      artwork_src: artwork[0]?.src,
      isSecureContext: typeof window !== 'undefined' && window.isSecureContext,
      protocol: typeof window !== 'undefined' && window.location.protocol
    });

    const safe = (name: MediaSessionAction, fn: () => void) => {
      try {
        navigator.mediaSession.setActionHandler(name, fn);
      } catch {
        // navegador no soporta esta acción, no pasa nada
      }
    };

    safe('play', () => this.audio?.play());
    safe('pause', () => this.audio?.pause());
    safe('nexttrack', () => this.next());
    safe('previoustrack', () => this.prev());
    safe('seekbackward', () => this.seek(Math.max(0, (this.audio?.currentTime ?? 0) - 10)));
    safe('seekforward', () =>
      this.seek(Math.min(this.audio?.duration ?? 0, (this.audio?.currentTime ?? 0) + 10))
    );
    try {
      navigator.mediaSession.setActionHandler('seekto', (d) => {
        if (d.seekTime !== undefined) this.seek(d.seekTime);
      });
    } catch {
      // ignorar
    }
  }

  private setPlaybackState(state: MediaSessionPlaybackState) {
    if (!this.hasMediaSession()) return;
    navigator.mediaSession.playbackState = state;
  }

  private updatePositionState() {
    if (!this.hasMediaSession() || !this.audio) return;
    if (!isFinite(this.audio.duration) || this.audio.duration <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration: this.audio.duration,
        position: this.audio.currentTime,
        playbackRate: this.audio.playbackRate || 1.0
      });
    } catch {
      // algunos navegadores fallan si los valores son raros, lo ignoramos
    }
  }
}

export const player = new PlayerState();
