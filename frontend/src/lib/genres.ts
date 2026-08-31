// Vocabulario canónico de géneros de bbeat y sus nombres para la UI.
//
// El backend guarda los géneros como slugs en minúsculas y sin acentos
// ("rap", "rnb", "bso", "electronica"): es lo que hace comparables las pistas
// entre fuentes. Pero enseñarlos tal cual queda mal ("Rnb", "Bso"). Aquí se
// traducen a su nombre de cara al usuario; un género desconocido (editado a
// mano fuera del vocabulario) se capitaliza y ya.
//
// El slug '__none__' es un valor especial de la API: pistas sin género.
export const SIN_GENERO = '__none__';

export const GENRE_LABELS: Record<string, string> = {
  rap: 'Rap / Hip-Hop',
  reggaeton: 'Reggaetón',
  rock: 'Rock',
  electronica: 'Electrónica',
  pop: 'Pop',
  latino: 'Latino',
  rnb: 'R&B / Soul',
  reggae: 'Reggae',
  metal: 'Metal',
  jazz: 'Jazz',
  blues: 'Blues',
  folk: 'Folk',
  clasica: 'Clásica',
  bso: 'Banda sonora',
  mundo: 'Músicas del mundo',
  infantil: 'Infantil',
  [SIN_GENERO]: 'Sin género'
};

/** Nombre de un género para la UI. Acepta null/'' (pistas sin género). */
export function genreLabel(genre: string | null | undefined): string {
  const g = (genre ?? '').trim().toLowerCase();
  if (!g) return GENRE_LABELS[SIN_GENERO];
  return GENRE_LABELS[g] ?? g.charAt(0).toUpperCase() + g.slice(1);
}

/** Slugs del vocabulario, para sugerir al editar una pista a mano. */
export const GENRE_SLUGS: string[] = Object.keys(GENRE_LABELS).filter((g) => g !== SIN_GENERO);
