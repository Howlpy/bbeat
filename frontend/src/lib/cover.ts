// Pide miniaturas al servidor: añade ?w=<ancho> a las URLs de carátulas de la
// API (/api/library/cover/...). Las URLs pueden traer ya ?v= y ?token=. Las
// locales (blob:, file:, capacitor) y las ajenas se devuelven tal cual.
export function coverSrc(url: string | null | undefined, w: number): string | undefined {
  if (!url) return undefined;
  if (!url.includes('/api/library/cover/')) return url;
  const hash = url.indexOf('#');
  const base = hash === -1 ? url : url.slice(0, hash);
  const tail = hash === -1 ? '' : url.slice(hash);
  const clean = base.replace(/([?&])w=\d+&?/, '$1').replace(/[?&]$/, '');
  return `${clean}${clean.includes('?') ? '&' : '?'}w=${w}${tail}`;
}
