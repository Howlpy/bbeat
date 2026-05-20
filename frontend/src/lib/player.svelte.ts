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
    });
    el.addEventListener('loadedmetadata', () => {
      this.duration = el.duration;
    });
    el.addEventListener('ended', () => this.next());
    el.addEventListener('play', () => {
      this.isPlaying = true;
      this.updateMediaSession();
    });
    el.addEventListener('pause', () => {
      this.isPlaying = false;
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
    if (autoplay) {
      this.audio.play().catch(() => {});
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

  private updateMediaSession() {
    if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
    const t = this.current;
    if (!t) return;

    const artwork = t.cover_url
      ? [{ src: t.cover_url, sizes: '512x512', type: 'image/jpeg' }]
      : [];

    navigator.mediaSession.metadata = new MediaMetadata({
      title: t.title,
      artist: t.artist_name,
      album: t.album_title ?? '',
      artwork
    });

    navigator.mediaSession.setActionHandler('play', () => this.toggle());
    navigator.mediaSession.setActionHandler('pause', () => this.toggle());
    navigator.mediaSession.setActionHandler('nexttrack', () => this.next());
    navigator.mediaSession.setActionHandler('previoustrack', () => this.prev());
    navigator.mediaSession.setActionHandler('seekto', (d) => {
      if (d.seekTime !== undefined) this.seek(d.seekTime);
    });
  }
}

export const player = new PlayerState();
