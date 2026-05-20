# 🎵 Bbeat

> Tu propio servidor de música personal. Self-hosted, ligero, mobile-first.

Bbeat es una alternativa minimalista a Navidrome con una diferencia clave:
**pegas una URL de Spotify y Bbeat descarga, etiqueta y organiza la pista
automáticamente** en tu servidor. Después la sirve por web a cualquier
dispositivo de tu red local.

- 🎧 WebApp 100% responsive, mobile-first — sin apps nativas.
- 📥 Importa desde Spotify (track, álbum, playlist) con metadata + carátula.
- 🗂️ Biblioteca organizada por artista/álbum en disco, en formatos abiertos.
- 🪶 Stack ligero: FastAPI + SQLite + SvelteKit. Levanta con un `docker compose up`.
- 🔧 Todo configurable desde la UI — wizard guiado en el primer arranque.

> ⚠️ Bbeat es para **uso personal en red local**. No expongas tu instancia a
> Internet y no redistribuyas contenido descargado.

## Estado del proyecto

🚧 **En desarrollo — Fase 0** (skeleton funcional).

| Fase | Estado |
|------|--------|
| 0. Skeleton + setup | 🚧 En curso |
| 1. Reproductor de biblioteca local | ⏳ |
| 2. Ingesta desde Spotify | ⏳ |
| 3. UX móvil + PWA | ⏳ |
| 4. Búsqueda, playlists, cola avanzada | ⏳ |

## Arrancar (modo desarrollo)

Necesitas: Python 3.12+, Node 20+, FFmpeg.

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edita tus credenciales de Spotify
python -m app.main         # http://localhost:8787

# Frontend (en otra terminal)
cd frontend
npm install
npm run dev                # http://localhost:5173
```

Luego abre **http://localhost:5173** y completa el wizard.

## Arrancar (Docker, recomendado)

```bash
git clone https://github.com/<tu-usuario>/bbeat.git
cd bbeat
cp backend/.env.example backend/.env
docker compose up -d
```

Abre **http://localhost:8787**.

## Stack

- **Backend**: FastAPI · SQLModel · SQLite · Spotipy · yt-dlp · Mutagen
- **Frontend**: SvelteKit · Tailwind v4 · TypeScript · PWA
- **Audio**: FFmpeg

## Estructura

```
bbeat/
├── backend/         # FastAPI + lógica de descarga
├── frontend/        # SvelteKit WebApp
├── data/            # Música, BD y secretos (gitignored)
├── docker-compose.yml
└── Dockerfile
```

## Licencia

MIT — ver [LICENSE](./LICENSE).
