import { Capacitor } from '@capacitor/core';
import { MediaSession } from '@capgo/capacitor-media-session';

// Capa unificada de Media Session.
//
// - App nativa (Capacitor/Android): usa @capgo/capacitor-media-session, que crea
//   la notificación/control de bloqueo NATIVO + un foreground service (el WebView
//   de Android no genera esa notificación por sí solo, a diferencia de Chrome).
// - Web (PWA): usa navigator.mediaSession del navegador.
//
// La API del plugin calca la web (pero con métodos async), así que el player
// llama a `media.*` sin enterarse de en qué plataforma corre.

const NATIVE = Capacitor.isNativePlatform();
const hasWeb = typeof navigator !== 'undefined' && 'mediaSession' in navigator;

export type PlaybackState = 'none' | 'paused' | 'playing';
export type MediaAction =
  | 'play' | 'pause' | 'previoustrack' | 'nexttrack'
  | 'seekbackward' | 'seekforward' | 'seekto' | 'stop';
export interface MediaArtwork { src: string; sizes?: string; type?: string }
export interface MediaMeta { title: string; artist: string; album?: string; artwork?: MediaArtwork[] }
export interface ActionDetails { seekTime?: number | null }

export const media = {
  available: NATIVE || hasWeb,

  setMetadata(m: MediaMeta) {
    if (NATIVE) { MediaSession.setMetadata(m).catch(() => {}); return; }
    if (hasWeb) navigator.mediaSession.metadata = new MediaMetadata(m as MediaMetadataInit);
  },

  setPlaybackState(state: PlaybackState) {
    if (NATIVE) { MediaSession.setPlaybackState({ playbackState: state }).catch(() => {}); return; }
    if (hasWeb) navigator.mediaSession.playbackState = state;
  },

  setActionHandler(action: MediaAction, handler: ((d: ActionDetails) => void) | null) {
    if (NATIVE) { MediaSession.setActionHandler({ action }, handler).catch(() => {}); return; }
    if (hasWeb) {
      try {
        navigator.mediaSession.setActionHandler(action as MediaSessionAction, handler as MediaSessionActionHandler | null);
      } catch {
        // el navegador no soporta esta acción, no pasa nada
      }
    }
  },

  setPositionState(s: { duration: number; position: number; playbackRate: number }) {
    if (NATIVE) { MediaSession.setPositionState(s).catch(() => {}); return; }
    if (hasWeb) {
      try {
        navigator.mediaSession.setPositionState(s);
      } catch {
        // valores raros: ignorar
      }
    }
  }
};
