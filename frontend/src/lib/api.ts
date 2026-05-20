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
};

export type Album = {
  id: number;
  title: string;
  year: number | null;
  artist_id: number;
  artist_name: string;
  track_count: number;
  cover_url: string | null;
};

export type Artist = {
  id: number;
  name: string;
  album_count: number;
  track_count: number;
};

export type LibraryStats = {
  tracks: number;
  albums: number;
  artists: number;
  total_bytes: number;
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

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json() as Promise<T>;
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
  backend_used: 'votify' | 'yt-dlp' | null;
  error: string | null;
  result_track_id: number | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type IngestResult = {
  kind: 'track' | 'album' | 'playlist';
  name: string;
  total_tracks: number;
  created_job_ids: number[];
  skipped_track_ids: string[];
};

export type SpotifyAuthStatus = {
  cookies_configured: boolean;
  cookies_path: string;
  size?: number;
  mtime?: number;
};

export const api = {
  health: () => json<{ status: string; version: string; setup_complete: boolean }>('/api/health'),
  stats: () => json<LibraryStats>('/api/library/stats'),

  tracks: (params: { limit?: number; offset?: number; artist_id?: number; album_id?: number } = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
    return json<{ total: number; limit: number; offset: number; items: Track[] }>(
      `/api/library/tracks?${q.toString()}`
    );
  },
  albums: () => json<{ total: number; items: Album[] }>('/api/library/albums'),
  artists: () => json<{ total: number; items: Artist[] }>('/api/library/artists'),

  startScan: () => json<{ started: boolean; reason?: string; state: ScanState }>(
    '/api/library/scan',
    { method: 'POST' }
  ),
  scanStatus: () => json<ScanState>('/api/library/scan/status'),

  // ── Ingesta Spotify ──
  ingest: (url: string) =>
    json<IngestResult>('/api/ingest', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ url })
    }),
  listJobs: (limit = 100) =>
    json<{ total: number; items: Job[] }>(`/api/jobs?limit=${limit}`),
  retryJob: (id: number) => json<{ ok: boolean }>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  deleteJob: (id: number) => json<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }),

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
