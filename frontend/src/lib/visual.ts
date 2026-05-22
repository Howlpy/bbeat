// Utilidades visuales: color dominante de una imagen + avatares de degradado.

/** Color medio (dominante aproximado) de una imagen same-origin, vía canvas. */
export function dominantColor(url: string): Promise<[number, number, number]> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      try {
        const n = 12;
        const c = document.createElement('canvas');
        c.width = n;
        c.height = n;
        const ctx = c.getContext('2d');
        if (!ctx) return resolve([30, 41, 59]);
        ctx.drawImage(img, 0, 0, n, n);
        const d = ctx.getImageData(0, 0, n, n).data;
        let r = 0, g = 0, b = 0, count = 0;
        for (let i = 0; i < d.length; i += 4) {
          if (d[i + 3] < 128) continue;
          r += d[i];
          g += d[i + 1];
          b += d[i + 2];
          count++;
        }
        if (!count) return resolve([30, 41, 59]);
        resolve([Math.round(r / count), Math.round(g / count), Math.round(b / count)]);
      } catch (e) {
        reject(e);
      }
    };
    img.onerror = reject;
    img.src = url;
  });
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Tono (0-360) determinista a partir de un texto. */
export function hueFor(seed: string): number {
  return hash(seed) % 360;
}

/** Degradado determinista para avatares de artista. */
export function avatarGradient(seed: string): string {
  const h1 = hueFor(seed);
  const h2 = (h1 + 45) % 360;
  return `linear-gradient(135deg, hsl(${h1} 58% 48%), hsl(${h2} 62% 30%))`;
}

/** Iniciales (1-2 letras) de un nombre. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase()) || '?';
}
