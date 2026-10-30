import { Capacitor } from '@capacitor/core';
import { coverSrc } from '$lib/cover';
import { COLORS, INK, PAPER, fmtNum, periodTitle, type ShareData } from './model';

const W = 1080;
const H = 1920;
const FONT = '"Manrope Variable", system-ui, sans-serif';
const M = 90; // margen lateral

/** Descarga la carátula como blob: evita canvas "tainted" (en nativo el origen es https://localhost). */
async function loadCover(url: string | null | undefined): Promise<ImageBitmap | null> {
  const src = coverSrc(url, 800);
  if (!src) return null;
  try {
    const res = await fetch(src);
    if (!res.ok) return null;
    return await createImageBitmap(await res.blob());
  } catch {
    return null;
  }
}

function rr(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

/** Recorta el texto con "…" hasta que quepa en `max` px. */
function clip(ctx: CanvasRenderingContext2D, text: string, max: number): string {
  if (ctx.measureText(text).width <= max) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(t + '…').width > max) t = t.slice(0, -1);
  return t.trimEnd() + '…';
}

/** Reduce el tamaño de fuente hasta que `text` quepa en `max` px. */
function fit(ctx: CanvasRenderingContext2D, text: string, weight: number, size: number, max: number) {
  let s = size;
  ctx.font = `${weight} ${s}px ${FONT}`;
  while (s > 24 && ctx.measureText(text).width > max) {
    s -= 2;
    ctx.font = `${weight} ${s}px ${FONT}`;
  }
  return s;
}

/** Parte en líneas (máx. `lines`) para texto largo; la última se recorta. */
function wrap(ctx: CanvasRenderingContext2D, text: string, max: number, lines: number): string[] {
  const words = text.split(/\s+/);
  const out: string[] = [];
  let cur = '';
  for (let i = 0; i < words.length; i++) {
    const next = cur ? `${cur} ${words[i]}` : words[i];
    if (ctx.measureText(next).width <= max || !cur) {
      cur = next;
    } else {
      out.push(cur);
      cur = words[i];
      if (out.length === lines - 1) {
        cur = words.slice(i).join(' ');
        break;
      }
    }
  }
  out.push(clip(ctx, cur, max));
  return out;
}

/** Marca de bbeat: las cinco barras del icono.svg. */
function drawMark(ctx: CanvasRenderingContext2D, x: number, y: number, size: number) {
  const k = size / 512;
  ctx.fillStyle = INK;
  rr(ctx, x, y, size, size, 120 * k);
  ctx.fill();
  ctx.fillStyle = COLORS.teal;
  for (const [bx, by, bh] of [
    [96, 216, 150],
    [168, 140, 226],
    [240, 96, 270],
    [312, 170, 196],
    [384, 240, 126]
  ]) {
    rr(ctx, x + bx * k, y + by * k, 48 * k, bh * k, 24 * k);
    ctx.fill();
  }
  ctx.fillStyle = '#abdbe1';
  ctx.beginPath();
  ctx.arc(x + 264 * k, y + 366 * k, 22 * k, 0, Math.PI * 2);
  ctx.fill();
}

function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color = INK) {
  ctx.font = `800 30px ${FONT}`;
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.65;
  ctx.fillText(text.toUpperCase(), x, y);
  ctx.globalAlpha = 1;
}

/** Dibuja el resumen en un canvas 1080x1920 (formato story). */
export async function renderSummary({ w, username }: ShareData): Promise<Blob> {
  if (document.fonts) {
    await Promise.all(
      [500, 700, 800].map((wt) => document.fonts.load(`${wt} 40px "Manrope Variable"`).catch(() => []))
    );
    await document.fonts.ready;
  }
  const song = w.top_tracks[0];
  const cover = await loadCover(song?.cover_url);

  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  ctx.textBaseline = 'alphabetic';

  // Fondo plano
  ctx.fillStyle = COLORS.teal;
  ctx.fillRect(0, 0, W, H);

  // Cabecera: marca + periodo
  drawMark(ctx, M, 90, 110);
  ctx.fillStyle = INK;
  ctx.font = `800 58px ${FONT}`;
  ctx.fillText('bbeat', M + 140, 168);
  ctx.font = `800 30px ${FONT}`;
  const tag = 'WRAPPED';
  const tw = ctx.measureText(tag).width + 56;
  ctx.fillStyle = INK;
  rr(ctx, W - M - tw, 112, tw, 66, 33);
  ctx.fill();
  ctx.fillStyle = COLORS.teal;
  ctx.fillText(tag, W - M - tw + 28, 156);

  // Título
  ctx.fillStyle = INK;
  const title = `Mi ${periodTitle(w.period)} en bbeat`;
  fit(ctx, title, 800, 100, W - M * 2);
  ctx.fillText(title, M, 340);

  // Canción top: carátula + texto
  const cs = 440;
  const cy = 420;
  if (cover) {
    ctx.save();
    rr(ctx, M, cy, cs, cs, 36);
    ctx.clip();
    ctx.drawImage(cover, 0, 0, cover.width, cover.height, M, cy, cs, cs);
    ctx.restore();
  } else {
    ctx.fillStyle = INK;
    rr(ctx, M, cy, cs, cs, 36);
    ctx.fill();
    drawMark(ctx, M + cs / 2 - 70, cy + cs / 2 - 70, 140);
  }
  const tx = M + cs + 50;
  const tmax = W - M - tx;
  label(ctx, 'Canción top', tx, cy + 50);
  ctx.fillStyle = INK;
  ctx.font = `800 62px ${FONT}`;
  const lines = song ? wrap(ctx, song.title, tmax, 3) : ['—'];
  lines.forEach((l, i) => ctx.fillText(l, tx, cy + 130 + i * 72));
  const ly = cy + 130 + lines.length * 72;
  ctx.font = `600 38px ${FONT}`;
  ctx.globalAlpha = 0.75;
  if (song) ctx.fillText(clip(ctx, song.artist_name, tmax), tx, ly + 6);
  ctx.globalAlpha = 1;
  if (song) {
    ctx.font = `800 38px ${FONT}`;
    ctx.fillText(`${fmtNum(song.plays)} plays`, tx, cy + cs - 6);
  }

  // Bloques: artista y género
  const by = 960;
  const bw = (W - M * 2 - 30) / 2;
  const bh = 250;
  const blocks: [string, string, string][] = [
    ['Artista top', w.top_artists[0]?.name ?? '—', w.top_artists[0] ? `${fmtNum(w.top_artists[0].plays)} plays` : ''],
    w.genres[0]
      ? ['Género top', w.genres[0].name, `${w.genres[0].pct}% de tu música`]
      : ['Pistas distintas', fmtNum(w.unique_tracks), `${fmtNum(w.unique_artists)} artistas`]
  ];
  blocks.forEach(([lab, main, sub], i) => {
    const bx = M + i * (bw + 30);
    ctx.fillStyle = INK;
    rr(ctx, bx, by, bw, bh, 36);
    ctx.fill();
    label(ctx, lab, bx + 36, by + 56, PAPER);
    ctx.fillStyle = COLORS.teal;
    const size = fit(ctx, main, 800, 62, bw - 72);
    ctx.fillText(clip(ctx, main, bw - 72), bx + 36, by + 56 + 30 + size);
    ctx.font = `600 32px ${FONT}`;
    ctx.fillStyle = PAPER;
    ctx.globalAlpha = 0.7;
    ctx.fillText(sub, bx + 36, by + bh - 36);
    ctx.globalAlpha = 1;
  });

  // Minutos: el número grande
  ctx.fillStyle = INK;
  label(ctx, 'Minutos escuchados', M, 1320);
  ctx.fillStyle = INK;
  const mins = fmtNum(w.total_minutes);
  const msize = fit(ctx, mins, 800, 300, W - M * 2);
  ctx.fillText(mins, M - 8, 1320 + 40 + msize * 0.78);

  // Fila de cifras
  const facts: [string, string][] = [
    [fmtNum(w.total_plays), 'plays'],
    [fmtNum(w.unique_artists), 'artistas']
  ];
  if (w.best_streak > 1) facts.push([`${w.best_streak}`, 'días de racha']);
  const fy = 1690;
  const fw = (W - M * 2 - 30 * (facts.length - 1)) / facts.length;
  facts.forEach(([n, l], i) => {
    const fx = M + i * (fw + 30);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 6;
    rr(ctx, fx + 3, fy + 3, fw - 6, 110 - 6, 28);
    ctx.stroke();
    ctx.fillStyle = INK;
    ctx.font = `800 44px ${FONT}`;
    ctx.fillText(n, fx + 28, fy + 70);
    const nw = ctx.measureText(n).width;
    ctx.font = `600 28px ${FONT}`;
    ctx.globalAlpha = 0.75;
    ctx.fillText(clip(ctx, l, fw - 56 - nw - 14), fx + 28 + nw + 14, fy + 70);
    ctx.globalAlpha = 1;
  });

  // Pie
  ctx.fillStyle = INK;
  ctx.font = `800 34px ${FONT}`;
  ctx.fillText(clip(ctx, `@${username}`, 600), M, 1860);
  ctx.font = `600 30px ${FONT}`;
  ctx.globalAlpha = 0.7;
  const foot = 'bbeat.howl.wtf';
  ctx.fillText(foot, W - M - ctx.measureText(foot).width, 1860);
  ctx.globalAlpha = 1;

  cover?.close();
  return await new Promise<Blob>((res, rej) =>
    canvas.toBlob((b) => (b ? res(b) : rej(new Error('canvas vacío'))), 'image/png')
  );
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res((r.result as string).split(',')[1] ?? '');
    r.onerror = () => rej(r.error);
    r.readAsDataURL(blob);
  });
}

export type ShareResult = 'shared' | 'downloaded' | 'cancelled';

/** Comparte el PNG: hoja nativa en la app, Web Share con archivo en el navegador o descarga. */
export async function sharePng(blob: Blob, name = 'bbeat-wrapped.png'): Promise<ShareResult> {
  const text = 'Mi Wrapped de bbeat';
  if (Capacitor.isNativePlatform()) {
    try {
      const { Filesystem, Directory } = await import('@capacitor/filesystem');
      const { Share } = await import('@capacitor/share');
      await Filesystem.writeFile({ path: name, data: await blobToBase64(blob), directory: Directory.Cache });
      const { uri } = await Filesystem.getUri({ path: name, directory: Directory.Cache });
      await Share.share({ title: text, text, files: [uri], dialogTitle: 'Compartir Wrapped' });
      return 'shared';
    } catch (e) {
      if (/cancel/i.test(String((e as Error)?.message ?? e))) return 'cancelled';
      throw e;
    }
  }
  const file = new File([blob], name, { type: 'image/png' });
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: text, text });
      return 'shared';
    } catch (e) {
      if ((e as DOMException)?.name === 'AbortError') return 'cancelled';
      throw e;
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  return 'downloaded';
}
