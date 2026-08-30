import type { Track } from './api';

export type TrackSort =
  | 'original'
  | 'title-asc'
  | 'title-desc'
  | 'artist'
  | 'album'
  | 'genre'
  | 'duration-asc'
  | 'duration-desc';

export type SortOption = { value: TrackSort; label: string };

/** Orden por defecto de la vista; 'original' significa "como venga del servidor". */
export const TRACK_SORTS: SortOption[] = [
  { value: 'original', label: 'Orden original' },
  { value: 'title-asc', label: 'Título A → Z' },
  { value: 'title-desc', label: 'Título Z → A' },
  { value: 'artist', label: 'Artista' },
  { value: 'album', label: 'Álbum' },
  { value: 'genre', label: 'Género' },
  { value: 'duration-asc', label: 'Duración ↑' },
  { value: 'duration-desc', label: 'Duración ↓' }
];

const VALID = new Set<string>(TRACK_SORTS.map((o) => o.value));

export function isTrackSort(v: string): v is TrackSort {
  return VALID.has(v);
}

const collator = new Intl.Collator('es', { numeric: true, sensitivity: 'base' });

/** Compara texto opcional dejando siempre los vacíos al final. */
function compareOptionalText(a: string | null | undefined, b: string | null | undefined) {
  const av = a?.trim() ?? '';
  const bv = b?.trim() ?? '';
  if (!av && bv) return 1;
  if (av && !bv) return -1;
  return collator.compare(av, bv);
}

export function trackMatches(track: Track, query: string): boolean {
  if (!query) return true;
  return [track.title, track.artist_name, track.album_title, track.genre]
    .filter(Boolean)
    .some((value) => String(value).toLocaleLowerCase('es').includes(query));
}

/**
 * Devuelve una copia ordenada. 'original' no toca nada: es el orden que ya trae
 * el servidor (posición en la playlist, número de pista en el álbum…), que es
 * información que aquí no podemos reconstruir.
 */
export function sortTracks(tracks: Track[], sort: TrackSort): Track[] {
  if (sort === 'original') return tracks;

  return [...tracks].sort((a, b) => {
    let compared = 0;
    switch (sort) {
      case 'title-asc':
        compared = collator.compare(a.title, b.title);
        break;
      case 'title-desc':
        compared = collator.compare(b.title, a.title);
        break;
      case 'artist':
        compared = collator.compare(a.artist_name, b.artist_name);
        break;
      case 'album':
        compared = compareOptionalText(a.album_title, b.album_title);
        break;
      case 'genre':
        compared = compareOptionalText(a.genre, b.genre);
        break;
      case 'duration-asc':
      case 'duration-desc': {
        const ad = a.duration_ms;
        const bd = b.duration_ms;
        if (ad == null && bd != null) compared = 1;
        else if (ad != null && bd == null) compared = -1;
        else if (ad != null && bd != null) {
          compared = sort === 'duration-asc' ? ad - bd : bd - ad;
        }
        break;
      }
    }
    // Desempate estable por título: dos artistas iguales no deben bailar entre
    // recargas de la misma lista.
    return compared || collator.compare(a.title, b.title);
  });
}
