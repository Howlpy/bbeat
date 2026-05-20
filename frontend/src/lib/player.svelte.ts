import type { Track } from './api';

class PlayerState {
  queue = $state<Track[]>([]);
  index = $state(0);
  isPlaying = $state(false);
  position = $state(0);
  duration = $state(0);
  volume = $state(1);

  current = $derived<Track | null>(this.queue[this.index] ?? null);

  audio: HTMLAudioElement | null = null;

  attach(el: HTMLAudioElement) {
    this.audio = el;
    el.volume = this.volume;

    el.addEventListener('timeupdate', () => {
      this.position = el.currentTime;
      this.updatePositionState();
    });
    el.addEventListener('loadedmetadata', () => {
      this.duration = el.duration;
      this.updatePositionState();
    });
    el.addEventListener('ended', () => this.next());
    el.addEventListener('play', () => {
      this.isPlaying = true;
      this.setPlaybackState('playing');
    });
    el.addEventListener('pause', () => {
      this.isPlaying = false;
      this.setPlaybackState('paused');
    });
  }

  playTracks(tracks: Track[], startIndex = 0) {
    this.queue = tracks;
    this.index = Math.max(0, Math.min(startIndex, tracks.length - 1));
    this.loadCurrent(true);
  }

  enqueue(track: Track) {
    this.queue = [...this.queue, track];
  }

  private loadCurrent(autoplay: boolean) {
    if (!this.audio || !this.current) return;
    this.audio.src = this.current.stream_url;
    this.audio.load();
    // metadata DEBE ir antes del .play() para que el OS enganche la sesión
    this.updateMediaSession();
    if (autoplay) {
      this.audio.play().catch((err) => {
        console.warn('autoplay rechazado:', err);
      });
    }
  }

  toggle() {
    if (!this.audio) return;
    if (this.audio.paused) this.audio.play();
    else this.audio.pause();
  }

  next() {
    if (this.index < this.queue.length - 1) {
      this.index += 1;
      this.loadCurrent(true);
    } else {
      this.audio?.pause();
      this.isPlaying = false;
    }
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
    if (this.audio) this.audio.volume = this.volume;
  }

  // ─── Media Session API ────────────────────────────────────────
  private hasMediaSession(): boolean {
    return typeof navigator !== 'undefined' && 'mediaSession' in navigator;
  }

  private updateMediaSession() {
    if (!this.hasMediaSession()) return;
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
