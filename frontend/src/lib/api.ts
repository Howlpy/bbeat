export type Track = {
  id: number;
  title: string;
  artist_id: number;
  artist_name: string;
  album_id: number | null;
  album_title: string | null;
  album_year: number | null;
  cover_url: string | null;
  track_number: number | null;
  disc_number: number | null;
  duration_ms: number | null;
  file_format: string | null;
  stream_url: string;
  source_url: string | null;
  liked?: boolean;
};

export type AlbumKind = 'album' | 'playlist';

export type Album = {
  id: number;
  title: string;
  year: number | null;
  artist_id: number;
  artist_name: string;
  track_count: number;
  cover_url: string | null;
  owner_id?: number | null;
  kind?: AlbumKind;
  is_mine?: boolean;
  is_saved?: boolean;
};

export type Artist = {
  id: number;
  name: string;
  album_count: number;
  track_count: number;
};

export type StatsBlock = {
  tracks: number;
  albums: number;
  artists: number;
  total_bytes: number;
};

export type LibraryStats = StatsBlock & {
  mine: StatsBlock;
  global: StatsBlock;
};

export type ScanState = {
  running: boolean;
  started_at: number | null;
  finished_at: number | null;
  total_files: number;
  processed: number;
  added: number;
  updated: number;
  removed: number;
  errors: string[];
};

import { auth } from './auth.svelte';
import { goto } from '$app/navigation';
import { apiUrl } from './config';
import { net, OfflineError } from './net.svelte';

/** Añade ?token=XXX a URLs internas /api/library/cover|stream para que <img> y <audio>
 * (que no pueden mandar Authorization header) puedan acceder. En la app nativa
 * además las hace absolutas contra API_BASE (no hay backend en el mismo origen). */
function tokenizeUrls(node: any): any {
  if (node === null || node === undefined) return node;
  if (typeof node === 'string') {
    if (auth.token && (node.startsWith('/api/library/stream/') || node.startsWith('/api/library/cover/'))) {
      const sep = node.includes('?') ? '&' : '?';
      return `${apiUrl(node)}${sep}token=${encodeURIComponent(auth.token)}`;
    }
    return node;
  }
  if (Array.isArray(node)) return node.map(tokenizeUrls);
  if (typeof node === 'object') {
    const out: Record<string, unknown> = {};
    for (const k in node) out[k] = tokenizeUrls(node[k]);
    return out;
  }
  return node;
}

async function json<T>(url: string, init?: RequestInit & { timeoutMs?: number; skipAuth?: boolean }): Promise<T> {
  const { timeoutMs = 30_000, skipAuth = false, ...fetchInit } = init ?? {};
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  // Inyecta Authorization si tenemos token y no es un endpoint público
  const headers = new Headers(fetchInit.headers as HeadersInit);
  if (!skipAuth && auth.token) {
    headers.set('Authorization', `Bearer ${auth.token}`);
  }
  try {
    const res = await fetch(apiUrl(url), { ...fetchInit, headers, signal: ctrl.signal });
    net.online = true; // hubo respuesta del servidor → hay red
    if (res.status === 401 && !skipAuth) {
      // Token inválido/expirado → logout y redirect
      auth.logout();
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        goto('/login');
      }
    }
    if (!res.ok) {
      let detail = '';
      try {
        const data = await res.clone().json();
        detail = typeof data?.detail === 'string' ? ` — ${data.detail}` : '';
      } catch {
        try {
          const t = await res.text();
          detail = t ? ` — ${t.slice(0, 200)}` : '';
        } catch {}
      }
      throw new Error(`${res.status} ${res.statusText}${detail}`);
    }
    const data = await res.json();
    return tokenizeUrls(data) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error(`Tiempo agotado (${Math.round(timeoutMs / 1000)}s) — ${url}`);
    }
    // fetch lanza TypeError cuando no se pudo establecer la conexión (sin red,
    // DNS, etc.). Lo normalizamos a un error de offline reconocible y amable.
    if (e instanceof TypeError) {
      net.online = false;
      throw new OfflineError();
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export type Job = {
  id: number;
  source_url: string;
  source_kind: 'track' | 'album' | 'playlist';
  spotify_track_id: string;
  title: string;
  artist: string;
  album: string;
  duration_ms: number | null;
  cover_url: string | null;
  status: 'pending' | 'running' | 'done' | 'failed';
  progress: number;          // 0-100
  stage: string | null;      // "descargando", "convirtiendo", "etiquetando"…
  backend_used: 'votify' | 'yt-dlp' | null;
  error: string | null;
  result_track_id: number | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type DedupItem = {
  spotify_id: string;
  title: string;
  track_id: number;
  added_to_album_id: number | null;
};

export type IngestResult = {
  kind: 'track' | 'album' | 'playlist';
  name: string;
  total_tracks: number;
  created_job_ids: number[];
  deduped: DedupItem[];
  skipped_track_ids: string[];
};

export type Source = 'spotify' | 'youtube' | 'soundcloud' | 'unknown';

export type IngestPreview = {
  source: Source;
  kind: 'track' | 'album' | 'playlist';
  name: string;
  total_tracks: number;
  tracks: {
    spotify_id: string;
    title: string;
    artists: string[];
    album: string;
    duration_ms: number;
    cover_url: string | null;
    track_number: number;
  }[];
};

export type IngestOverrides = {
  album?: string;
  artist?: string;
  album_artist?: string;
  year?: number;
  cover_url?: string;
  target_album_id?: number;
};

export type JobStats = {
  pending: number;
  running: number;
  done: number;
  failed: number;
  total: number;
};

export type SpotifyAuthStatus = {
  cookies_configured: boolean;
  cookies_path: string;
  size?: number;
  mtime?: number;
};

export const api = {
  health: () => json<{ status: string; version: string; setup_complete: boolean }>('/api/health', { skipAuth: true }),

  // ── Auth ──
  register: (username: string, email: string, password: string) =>
    json<{ token?: string; user: import('./auth.svelte').AuthUser; pending?: boolean }>('/api/auth/register', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username, email, password }),
      skipAuth: true
    }),
  login: (login: string, password: string) =>
    json<{ token: string; user: import('./auth.svelte').AuthUser }>('/api/auth/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ login, password }),
      skipAuth: true
    }),
  me: () => json<import('./auth.svelte').AuthUser>('/api/auth/me'),
  listUsers: () =>
    json<{ total: number; items: import('./auth.svelte').AuthUser[] }>('/api/admin/users'),
  updateUser: (id: number, body: { is_active?: boolean; is_admin?: boolean; is_approved?: boolean }) =>
    json<import('./auth.svelte').AuthUser>(`/api/admin/users/${id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }),
  deleteUser: (id: number) =>
    json<{ ok: boolean }>(`/api/admin/users/${id}`, { method: 'DELETE' }),
  stats: () => json<LibraryStats>('/api/library/stats'),

  tracks: (params: { limit?: number; offset?: number; artist_id?: number; album_id?: number } = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
    return json<{ total: number; limit: number; offset: number; items: Track[] }>(
      `/api/library/tracks?${q.toString()}`
    );
  },
  albums: (
    scope: 'saved' | 'all' | 'mine' = 'saved',
    opts: { q?: string; kind?: AlbumKind } = {}
  ) => {
    const p = new URLSearchParams({ scope });
    if (opts.q) p.set('q', opts.q);
    if (opts.kind) p.set('kind', opts.kind);
    return json<{ total: number; items: Album[] }>(`/api/library/albums?${p.toString()}`);
  },
  album: (id: number) => json<Album>(`/api/library/albums/${id}`),
  saveAlbum: (id: number) =>
    json<{ saved: boolean }>(`/api/library/albums/${id}/save`, { method: 'PUT' }),
  unsaveAlbum: (id: number) =>
    json<{ saved: boolean }>(`/api/library/albums/${id}/save`, { method: 'DELETE' }),
  artists: () => json<{ total: number; items: Artist[] }>('/api/library/artists'),
  recent: (limit = 12) =>
    json<{ tracks: Track[]; albums: Album[] }>(`/api/library/recent?limit=${limit}`),

  startScan: () => json<{ started: boolean; reason?: string; state: ScanState }>(
    '/api/library/scan',
    { method: 'POST' }
  ),
  scanStatus: () => json<ScanState>('/api/library/scan/status'),

  // ── Ingesta (Spotify / YouTube / SoundCloud) ──
  previewIngest: (url: string) =>
    json<IngestPreview>('/api/ingest/preview', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ url }),
      timeoutMs: 60_000  // playlists grandes pueden tardar
    }),
  ingest: (url: string, overrides?: IngestOverrides, onlyIds?: string[]) =>
    json<IngestResult & { source?: Source }>('/api/ingest', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ url, overrides, only_ids: onlyIds }),
      timeoutMs: 60_000
    }),
  addTracksToAlbum: (albumId: number, trackIds: number[]) =>
    json<{ added: number; already: number; denied: number }>(
      `/api/library/albums/${albumId}/tracks`,
      {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ track_ids: trackIds })
      }
    ),

  uploadAlbumCover: async (albumId: number, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return json<{ ok: boolean; cover_url: string; tracks_updated: number }>(
      `/api/library/albums/${albumId}/cover`,
      { method: 'POST', body: fd }
    );
  },

  // ── Edición / borrado ──
  deleteTrack: (id: number) =>
    json<{ ok: boolean }>(`/api/library/tracks/${id}`, { method: 'DELETE' }),
  editTrack: (
    id: number,
    body: {
      title?: string;
      artist?: string;
      album?: string;
      track_number?: number;
      disc_number?: number;
      year?: number;
      target_album_id?: number;
    }
  ) =>
    json<{ ok: boolean }>(`/api/library/tracks/${id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }),
  deleteAlbum: (id: number) =>
    json<{ deleted: boolean; tracks_deleted: number }>(`/api/library/albums/${id}`, {
      method: 'DELETE'
    }),
  createAlbum: (body: { title: string; artist?: string; year?: number; kind?: AlbumKind }) =>
    json<Album>('/api/library/albums', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }),
  editAlbum: (id: number, body: { title?: string; year?: number }) =>
    json<{ ok: boolean }>(`/api/library/albums/${id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body)
    }),

  // ── Búsqueda ──
  search: (q: string, limit = 50) =>
    json<{ query: string; total: number; items: Track[] }>(
      `/api/library/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),

  // ── Letras ──
  lyrics: (trackId: number) =>
    json<{
      found: boolean;
      plain: string | null;
      synced: string | null;
      source: string;
      track_name?: string;
      artist_name?: string;
    }>(`/api/library/tracks/${trackId}/lyrics`, { timeoutMs: 15_000 }),

  // ── Me gusta / historial ──
  likeTrack: (id: number) =>
    json<{ liked: boolean }>(`/api/library/tracks/${id}/like`, { method: 'PUT' }),
  unlikeTrack: (id: number) =>
    json<{ liked: boolean }>(`/api/library/tracks/${id}/like`, { method: 'DELETE' }),
  likedTracks: () => json<{ total: number; items: Track[] }>('/api/library/liked'),
  recordPlay: (id: number) =>
    json<{ ok: boolean }>(`/api/library/tracks/${id}/play`, { method: 'POST' }),
  topTracks: (opts: { limit?: number; days?: number; scope?: 'me' | 'server' } = {}) => {
    const q = new URLSearchParams();
    if (opts.limit !== undefined) q.set('limit', String(opts.limit));
    if (opts.days !== undefined) q.set('days', String(opts.days));
    if (opts.scope !== undefined) q.set('scope', opts.scope);
    const s = q.toString();
    return json<{ items: (Track & { plays: number })[] }>(`/api/library/top${s ? '?' + s : ''}`);
  },
  history: (limit = 50) =>
    json<{ items: (Track & { last_played: string | null })[] }>(
      `/api/library/history?limit=${limit}`
    ),
  myStats: (days?: number) =>
    json<{
      total_plays: number;
      total_minutes: number;
      unique_tracks: number;
      liked_count: number;
      top_tracks: (Track & { plays: number })[];
      top_artists: { id: number; name: string; plays: number }[];
    }>(`/api/library/me/stats${days ? '?days=' + days : ''}`),
  activity: (limit = 30) =>
    json<{ items: (Track & { username: string; played_at: string | null })[] }>(
      `/api/library/activity?limit=${limit}`
    ),

  // ── Upload local ──
  uploadTrack: async (
    file: File,
    opts: { title?: string; album?: string; artist?: string; year?: number; target_album_id?: number } = {}
  ) => {
    const fd = new FormData();
    fd.append('file', file);
    if (opts.title) fd.append('title', opts.title);
    if (opts.album) fd.append('album', opts.album);
    if (opts.artist) fd.append('artist', opts.artist);
    if (opts.year !== undefined) fd.append('year', String(opts.year));
    if (opts.target_album_id !== undefined) fd.append('target_album_id', String(opts.target_album_id));
    return json<{ ok: boolean; track_id: number; title: string; artist: string; album: string }>(
      '/api/library/upload',
      { method: 'POST', body: fd, timeoutMs: 120_000 }
    );
  },
  listJobs: (limit = 100) =>
    json<{ total: number; items: Job[]; stats: JobStats }>(`/api/jobs?limit=${limit}`),
  jobStats: () => json<JobStats>('/api/jobs/stats'),
  retryJob: (id: number) => json<{ ok: boolean }>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  retryFailed: () => json<{ retried: number }>('/api/jobs/retry-failed', { method: 'POST' }),
  deleteJob: (id: number) => json<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }),
  clearJobs: (status?: 'failed' | 'done' | 'pending') => {
    const q = status ? `?status=${status}` : '';
    return json<{ deleted: number }>(`/api/jobs${q}`, { method: 'DELETE' });
  },

  // ── Cookies Spotify (Votify) ──
  spotifyAuthStatus: () => json<SpotifyAuthStatus>('/api/auth/spotify/status'),
  uploadCookies: async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return json<{ ok: boolean; size: number }>('/api/auth/spotify/cookies', {
      method: 'POST',
      body: fd
    });
  },
  deleteCookies: () => json<{ ok: boolean }>('/api/auth/spotify/cookies', { method: 'DELETE' })
};

export function formatDuration(ms: number | null): string {
  if (!ms) return '—';
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}
