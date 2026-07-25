import { Capacitor, registerPlugin } from '@capacitor/core';

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
  | 'seekbackward' | 'seekforward' | 'seekto' | 'stop' | 'playfrommediaid';
export interface MediaArtwork { src: string; sizes?: string; type?: string }
export interface MediaMeta { title: string; artist: string; album?: string; artwork?: MediaArtwork[] }
export interface ActionDetails { seekTime?: number | null; index?: number | null }

type AutoQueueItem = MediaMeta & { id: number; artwork?: MediaArtwork[]; queueIndex?: number };

interface BbeatAutoPlugin {
  setMetadata(options: MediaMeta): Promise<void>;
  setPlaybackState(options: { playbackState: PlaybackState }): Promise<void>;
  setPositionState(options: { duration: number; position: number; playbackRate: number }): Promise<void>;
  setQueue(options: { items: AutoQueueItem[]; currentIndex: number }): Promise<void>;
  addListener(
    eventName: 'action',
    listener: (event: { action: MediaAction; seekTime?: number; index?: number }) => void
  ): Promise<{ remove: () => Promise<void> }>;
}

const AutoSession = registerPlugin<BbeatAutoPlugin>('BbeatAuto');
const nativeHandlers = new Map<MediaAction, ((d: ActionDetails) => void) | null>();
let nativeListenerReady = false;

function ensureNativeListener() {
  if (!NATIVE || nativeListenerReady) return;
  nativeListenerReady = true;
  AutoSession.addListener('action', (event) => {
    nativeHandlers.get(event.action)?.({ seekTime: event.seekTime, index: event.index });
  }).catch(() => {
    nativeListenerReady = false;
  });
}

export const media = {
  available: NATIVE || hasWeb,

  setMetadata(m: MediaMeta) {
    if (NATIVE) { ensureNativeListener(); AutoSession.setMetadata(m).catch(() => {}); return; }
    if (hasWeb) navigator.mediaSession.metadata = new MediaMetadata(m as MediaMetadataInit);
  },

  setPlaybackState(state: PlaybackState) {
    if (NATIVE) { AutoSession.setPlaybackState({ playbackState: state }).catch(() => {}); return; }
    if (hasWeb) navigator.mediaSession.playbackState = state;
  },

  setActionHandler(action: MediaAction, handler: ((d: ActionDetails) => void) | null) {
    if (NATIVE) {
      ensureNativeListener();
      nativeHandlers.set(action, handler);
      return;
    }
    if (hasWeb) {
      try {
        navigator.mediaSession.setActionHandler(action as MediaSessionAction, handler as MediaSessionActionHandler | null);
      } catch {
        // el navegador no soporta esta acción, no pasa nada
      }
    }
  },

  setPositionState(s: { duration: number; position: number; playbackRate: number }) {
    if (NATIVE) { AutoSession.setPositionState(s).catch(() => {}); return; }
    if (hasWeb) {
      try {
        navigator.mediaSession.setPositionState(s);
      } catch {
        // valores raros: ignorar
      }
    }
  },

  setQueue(items: AutoQueueItem[], currentIndex: number) {
    if (!NATIVE) return;
    // MediaSession transporta la cola mediante Binder. Mandar una biblioteca
    // entera puede superar el límite de la transacción y cerrar Android al
    // comenzar a reproducir. Android Auto solo necesita una ventana próxima a
    // la pista actual; queueIndex conserva la posición en la cola completa.
    const maxNativeItems = 100;
    const maxStart = Math.max(0, items.length - maxNativeItems);
    const start = Math.min(Math.max(0, currentIndex - Math.floor(maxNativeItems / 2)), maxStart);
    const nativeItems = items
      .slice(start, start + maxNativeItems)
      .map((item, offset) => ({ ...item, queueIndex: start + offset }));
    AutoSession.setQueue({ items: nativeItems, currentIndex: currentIndex - start }).catch(() => {});
  }
};
