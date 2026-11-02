import { browser } from '$app/environment';
import { Capacitor } from '@capacitor/core';
import type { Track } from './api';

// Safari / PWA de iOS no decodifica Ogg Opus (o solo versiones recientes): para
// esas pistas pedimos al backend el audio transcodificado (?format=).

/** Formato al que se transcodifica: AAC en MP4, lo que Safari reproduce mejor. */
const FALLBACK_FORMAT = 'm4a';
const OGG_FORMATS = new Set(['opus', 'ogg', 'webm']);

let oggOpusOk: boolean | null = null;

/** ¿Puede este navegador reproducir Ogg Opus? (se calcula una sola vez). */
export function canPlayOggOpus(): boolean {
  if (oggOpusOk !== null) return oggOpusOk;
  if (!browser) return true;
  if (Capacitor.isNativePlatform()) return (oggOpusOk = true); // WebView de Android: siempre
  // WebKit de Apple (Safari, cualquier navegador de iOS): aunque algunas versiones
  // dicen soportar Ogg Opus, fallan al decodificarlo. Siempre transcodificado.
  if (/Apple/i.test(navigator.vendor || '') || /iP(hone|ad|od)/.test(navigator.userAgent)) {
    return (oggOpusOk = false);
  }
  try {
    oggOpusOk = document.createElement('audio').canPlayType('audio/ogg; codecs="opus"') !== '';
  } catch {
    oggOpusOk = true;
  }
  return oggOpusOk;
}

/** URL de streaming de la pista, transcodificada si el navegador no soporta su formato. */
export function streamUrlFor(t: Track): string {
  const fmt = (t.file_format || '').toLowerCase();
  if (!OGG_FORMATS.has(fmt) || canPlayOggOpus()) return t.stream_url;
  const sep = t.stream_url.includes('?') ? '&' : '?';
  return `${t.stream_url}${sep}format=${FALLBACK_FORMAT}`;
}
