// Tipos de la API admin de géneros con IA (/api/admin/ai-genres/*).

export type AiRunState = {
  running: boolean;
  total: number;
  done: number;
  applied: number;
  pending: number;
  skipped: number;
  errors: number;
  quota_exceeded: boolean;
  message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AiGenresStatus = {
  config: {
    enabled: boolean;
    provider: string;
    model: string;
    base_url_custom: boolean;
    api_key_set: boolean;
    rpm: number;
    min_confidence: number;
    search_provider: string;
    search_configured: boolean;
    artist_consistency: boolean;
  };
  tracks_without_genre: number;
  pending_suggestions: number;
  unclassified_artists: number;
  run: AiRunState;
};

export type AiSuggestion = {
  id: number;
  artist_id: number;
  artist_name: string;
  track_id: number | null;
  track_title: string | null;
  genre: string;
  genre_name: string;
  previous_genre: string | null;
  confidence: number;
  reason: string | null;
  status: string;
};
