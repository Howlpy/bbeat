# Bbeat

A self-hosted personal music server. Paste a Spotify, YouTube or SoundCloud URL and Bbeat downloads the audio, tags it, organizes it and serves it to your devices through a mobile-first web app, a native Android app, and the Subsonic API.

Bbeat is built for yourself or a small group of friends sharing one instance: every user has their own favorites, history and Wrapped, and can download tracks for offline listening.

> Exposing Bbeat to the internet is your responsibility (platform ToS, copyright). It has authentication, but rate limiting is not included yet.

## Features

- **Import** from Spotify, YouTube and SoundCloud (single tracks, albums, playlists, mixes with track deselection), plus local file upload. Duplicates are detected by source ID, then by title + artist + duration, and are linked instead of downloaded again. The import list shows who imported what.
- **Library** organized as `Artist/Album/NN - Title.ext`, with a Library hub (favorites, playlists and albums, artists, downloads, and genre cards). Multi-artist playlists are stored as a single "Various Artists" collection. Edit or delete tracks and albums from the UI; export a playlist or album as a `.zip`.
- **Player** with queue, shuffle/repeat, Media Session controls (lock screen), a full-screen Now Playing view with cover-based colors and synced lyrics (LRCLIB), and a gapless-friendly double `<audio>` setup.
- **Offline mode**: download tracks for offline listening (IndexedDB on the web, files on disk in the Android app). When the connection drops, Bbeat detects it immediately and keeps the same UI with non-downloaded tracks dimmed; playback continues with the downloaded tracks of the current queue.
- **Network resilience**: failed GET requests are retried, and data reloads when the connection comes back.
- **Genres**: a voting cascade (Last.fm, Deezer, iTunes, Wikidata) with per-artist consistency, genre cards in the Library, and an optional AI classifier. See [docs/genres.md](./docs/genres.md) and [docs/ai-genres.md](./docs/ai-genres.md).
- **Weekly genre charts**: "most played this week" per genre, computed over the last 7 days across the whole server. Tracks are ranked by distinct listeners first, then plays, filled up to 30 entries, and show who listened.
- **Wrapped**: stories-style recap per period (week, month, year, all time) with a shareable 1080x1920 image.
- **Multi-user**: JWT auth, admin approval of new accounts (the first user becomes admin), ban/promote, and live "now playing" so you can see what others are listening to.
- **Subsonic API** compatibility, so third-party clients (Amperfy, play:Sub, substreamer, Symfonium, DSub, Feishin...) work against your instance.
- **Android app** (Capacitor) with background playback, Android Auto, native offline storage and multi-server support.
- **Design and performance**: a calm design system (tokens, bundled Manrope font, no gradients); hashed assets served with immutable caching, WebP cover thumbnails (`?w=`), and SQLite tuned with WAL and pragmas.

Audio is downloaded from YouTube through yt-dlp. The Opus stream is preferred and copied without re-encoding.

The catalog is a **global pool**: tracks, albums, search and streaming are shared, so any authenticated user can see and play everything on the instance. What defines your personal library is what you **save**; an album's owner only controls who can edit it. This is meant for instances shared among people you trust.

## Stack

- **Backend**: FastAPI, SQLModel, SQLite, SpotifyScraper, yt-dlp, Mutagen, bcrypt, PyJWT, FFmpeg
- **Frontend**: SvelteKit 5, Tailwind 4, TypeScript, PWA (service worker)
- **Android**: Capacitor wrapping the same frontend, see [ANDROID.md](./ANDROID.md)

## Quick start (Docker Compose)

The provided `docker-compose.yml` runs the published image (`howl0y/bbeat:latest`), mounts `./data` as the library and reads `./backend/.env`.

```bash
git clone https://github.com/Howlpy/bbeat.git
cd bbeat
cp backend/.env.example backend/.env    # then edit as needed
mkdir -p data && sudo chown 1000:1000 data
docker compose up -d
```

Open `http://localhost:8787` and register. **The first user to register becomes admin**; later users wait for admin approval.

Notes:

- The container runs as `1000:1000` so files in `data/` are not owned by root. Change `user:` in the compose file if your uid differs.
- The compose file also carries a Watchtower label so the container can be updated automatically (`WATCHTOWER_LABEL_ENABLE=true`). Remove it if you do not use Watchtower.
- `docker compose build` builds the image locally instead of pulling it.
- Health check: `GET /api/health`.

### Without Docker

Requirements: Python 3.12+, Node 22+, FFmpeg.

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend (the backend serves the static build)
cd ../frontend
npm install
npm run build

# Run
cd ../backend
python -m app.main        # http://localhost:8787
```

For production, run it as a systemd service (use `loginctl enable-linger` so it survives reboots) or use Docker.

## Configuration

Everything is configured through environment variables, usually in `backend/.env` (see `backend/.env.example`). Defaults below are read from `backend/app/config.py`.

| Variable | Default | Notes |
|---|---|---|
| `BBEAT_HOST` | `0.0.0.0` | Bind address |
| `BBEAT_PORT` | `8787` | Bind port |
| `BBEAT_DEBUG` | `false` | `true` enables autoreload; do not use in production |
| `BBEAT_DATA_DIR` | `<repo>/data` | Root data directory |
| `BBEAT_MUSIC_DIR` | `<data>/music` | Music library |
| `BBEAT_COVERS_DIR` | `<data>/covers` | Cover art |
| `BBEAT_SECRETS_DIR` | `<data>/secrets` | JWT key and other secrets |
| `BBEAT_TRANSCACHE_DIR` | `<data>/transcache` | Transcoding cache |
| `BBEAT_DB_PATH` | `<data>/library.db` | SQLite database |
| `BBEAT_AUDIO_FORMAT` | `opus` | `opus`, `ogg`, `m4a`, `mp3` or `flac`. `opus` copies the source stream without re-encoding |
| `BBEAT_AUDIO_QUALITY` | `auto` | Quality hint for the download |
| `BBEAT_MAX_CONCURRENT_JOBS` | `1` | Parallel downloads (mind RAM on small hosts) |
| `BBEAT_TRANSCODE_CONCURRENCY` | `2` | Simultaneous ffmpeg processes for Subsonic transcoding |
| `BBEAT_TRANSCACHE_MAX_MB` | `1024` | Disk cap for the transcoding cache, least recently used files are purged (`0` = unlimited) |
| `BBEAT_CORS_ORIGINS` | `http://localhost:5173` | Extra allowed origins (comma separated). Native app WebView origins are always allowed |
| `BBEAT_LASTFM_API_KEY` | empty | Read-only Last.fm key used as a genre source; without it that source is skipped |
| `BBEAT_ARTIST_CONSISTENCY` | `true` | Keep an artist's genre when an imported track disagrees (works without AI) |
| `BBEAT_AI_PROVIDER` | `none` | `openai`, `gemini`, `anthropic`, `ollama` or `none` |
| `BBEAT_AI_API_KEY` | empty | Provider key (not needed for local Ollama / LM Studio) |
| `BBEAT_AI_MODEL` | per provider | See [docs/ai-genres.md](./docs/ai-genres.md) |
| `BBEAT_AI_BASE_URL` | per provider | Any OpenAI-compatible endpoint (use `openai` as provider) |
| `BBEAT_AI_RPM` | `10` | Requests per minute to the provider |
| `BBEAT_AI_TIMEOUT` | `60` | Seconds per request |
| `BBEAT_AI_MIN_CONFIDENCE` | `0.75` | Below this, suggestions go to the review queue instead of being applied |
| `BBEAT_AI_BATCH_ARTISTS` | `5` | Small artists grouped into one request to save quota |
| `BBEAT_SEARCH_PROVIDER` | `none` | `searxng` or `none` (web evidence for the AI classifier) |
| `BBEAT_SEARXNG_URL` | empty | For example `http://localhost:8080` (SearXNG needs its JSON format enabled) |

Secrets (JWT key, optional Spotify cookies) live in `data/secrets/` with `600` permissions. `data/` is meant to stay out of git.

## Android app

Download the latest `bbeat-X.Y.Z.apk` from the [Releases page](https://github.com/Howlpy/bbeat/releases) and install it (allow "install from unknown sources"). On first launch, enter the URL of your Bbeat server; several servers can be saved.

The app adds native offline downloads to disk, reliable background and lock-screen playback, Android Auto, a native icon and splash screen, and Android back button handling (back navigates inside the app instead of closing it). To build the APK yourself, see [ANDROID.md](./ANDROID.md).

## Subsonic clients

Bbeat implements the [Subsonic API](http://www.subsonic.org/pages/api.jsp), the de facto standard for self-hosted music servers. This is especially useful on iPhone, where there is no native Bbeat app.

1. In **Settings, Subsonic access**, generate your **token** (a secret separate from your password).
2. In the client, add a server with your instance URL, your username and the **token as the password**.

Browsing by artist/album/song, search, playlist create/edit/delete, favorites (star maps to "like") and scrobbling (which feeds your history and Wrapped) are supported. Playlists created from a Subsonic client are the same playlists you see in the Bbeat app, and deleting a playlist never deletes audio files.

Why a token instead of your password: Subsonic authentication requires the server to verify `md5(password + salt)`, but Bbeat stores passwords with bcrypt, which is not reversible. The dedicated token can be regenerated or revoked at any time.

By default the stream serves the Opus file as is. If a client asks for another format (`format=mp3|aac|ogg`), Bbeat transcodes on the fly with FFmpeg and caches the result. Tune it with `BBEAT_TRANSCODE_CONCURRENCY` and `BBEAT_TRANSCACHE_MAX_MB`.

## AI genre classifier (optional)

Disabled by default. When enabled, an LLM of your choice (Gemini, any OpenAI-compatible API such as OpenRouter or Groq, Anthropic, or local Ollama) reviews genres **per artist**, optionally using SearXNG web snippets as evidence. Confident answers are applied; the rest go to **Admin, AI genres, Review suggestions**. Genres you edit by hand are locked and never overwritten.

Quick example for Gemini (free key at <https://aistudio.google.com/apikey>):

```ini
BBEAT_AI_PROVIDER=gemini
BBEAT_AI_API_KEY=AIza...
```

Run a dry run (writes nothing) from the CLI:

```bash
cd backend
python -m scripts.ai_genres --limit 20 --report report.csv
```

Full details, provider examples and CLI options: [docs/ai-genres.md](./docs/ai-genres.md).

## Exposing it to the internet (optional)

The simplest option is to put it behind Cloudflare (proxied `A` record, router port forward, SSL/TLS in Flexible mode plus Always Use HTTPS). For better security use Cloudflare Tunnel with Access, which needs no open ports. Remember that rate limiting is not included yet.

## Development

```bash
# Backend (from backend/)
pip install -r requirements.txt -r requirements-dev.txt
python -m app.main                  # API on :8787
python -m pytest tests/ -q          # tests

# Frontend (from frontend/)
npm install
npm run dev                         # Vite dev server (proxy to the backend)
npm run check                       # svelte-check / type check
npm run build                       # static build served by the backend
```

Android build: `cd frontend && npm run apk` (requirements and signing details in [ANDROID.md](./ANDROID.md)).

## Roadmap

See [docs/ROADMAP.md](./docs/ROADMAP.md).

## Contributing

Issues and pull requests are welcome. Please open an issue first for larger changes, keep commits in [Conventional Commits](https://www.conventionalcommits.org/) style, and run the backend tests and `npm run check` before submitting.

## License

MIT, see [LICENSE](./LICENSE). Use is at your own risk: complying with each platform's terms of service and with copyright law is the operator's responsibility.
