import type { Wrapped, WrappedPeriod } from '$lib/api';

/** Colores planos (sin degradados) de cada diapositiva. */
export const INK = '#0b0d11';
export const PAPER = '#eef1f4';
export const COLORS = {
  teal: '#66b7c0',
  sand: '#e8c76a',
  coral: '#ee9079',
  lilac: '#b9a8ea',
  mint: '#82d6a8',
  sky: '#7ba8ee'
} as const;

export const PERIODS: { id: WrappedPeriod; label: string; sub: string; title: string }[] = [
  { id: 'week', label: 'Esta semana', sub: 'Últimos 7 días', title: 'semana' },
  { id: 'month', label: 'Este mes', sub: 'Últimos 30 días', title: 'mes' },
  { id: 'year', label: 'Este año', sub: 'Últimos 365 días', title: 'año' },
  { id: 'all', label: 'Todo', sub: 'Desde el primer play', title: 'historia' }
];

export function periodTitle(p: WrappedPeriod): string {
  return PERIODS.find((x) => x.id === p)?.title ?? '';
}

const DAYS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

export const fmtNum = (n: number) => n.toLocaleString('es-ES');

/** Franja del día en la que más escuchas (normalizada por horas de la franja). */
export function persona(hours: number[]): { title: string; text: string; peak: number } {
  const slots = [
    { from: 0, to: 6, title: 'Eres de madrugada', text: 'Cuando el mundo duerme, tú le das al play.' },
    { from: 6, to: 12, title: 'Eres de mañanas', text: 'Empiezas el día con música.' },
    { from: 12, to: 20, title: 'Eres de tardes', text: 'La banda sonora de tu tarde es bbeat.' },
    { from: 20, to: 24, title: 'Eres un búho nocturno', text: 'La noche se escucha mejor con música.' }
  ];
  let best = slots[0];
  let bestAvg = -1;
  for (const s of slots) {
    const avg = hours.slice(s.from, s.to).reduce((a, b) => a + b, 0) / (s.to - s.from);
    if (avg > bestAvg) {
      bestAvg = avg;
      best = s;
    }
  }
  const peak = hours.indexOf(Math.max(...hours));
  return { title: best.title, text: best.text, peak };
}

export function topWeekday(weekdays: number[]): string {
  return DAYS[weekdays.indexOf(Math.max(...weekdays))];
}

export type SlideKind =
  | 'intro'
  | 'minutes'
  | 'song'
  | 'songs'
  | 'artist'
  | 'genre'
  | 'time'
  | 'facts'
  | 'summary';

/** Solo las diapositivas que tienen datos. */
export function buildSlides(w: Wrapped): SlideKind[] {
  const s: SlideKind[] = ['intro', 'minutes'];
  if (w.top_tracks.length) s.push('song');
  if (w.top_tracks.length > 1) s.push('songs');
  if (w.top_artists.length) s.push('artist');
  if (w.genres.length) s.push('genre');
  if (Math.max(...w.hours) > 0) s.push('time');
  if (w.best_streak >= 2 || w.new_tracks > 0 || w.active_days > 1) s.push('facts');
  s.push('summary');
  return s;
}

export type ShareData = {
  w: Wrapped;
  username: string;
};
