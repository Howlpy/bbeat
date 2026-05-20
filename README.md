# Bbeat

Servidor de música personal self-hosted. Webapp responsive, mobile-first, que descarga música automáticamente desde URLs públicas y la sirve a tu navegador.

Pegas una URL de Spotify, YouTube o SoundCloud y Bbeat:

1. Extrae metadata sin auth (título, artista, álbum, carátula).
2. Descarga el audio (yt-dlp por defecto; Votify si subes cookies de cuenta Premium).
3. Etiqueta y organiza el fichero en `Artista/Álbum/NN - Título.ext`.
4. Lo indexa y lo deja listo para reproducir.
5. Si la pista ya existe en la biblioteca (mismo source ID), no la vuelve a descargar — solo la enlaza al álbum del usuario.

Pensado para uso personal o entre amigos en una instancia compartida. No es una alternativa a Spotify pública: es para tu música, en tu servidor.

> Aviso: no expongas Bbeat a internet sin entender los riesgos (ToS de las plataformas, copyright). Si lo haces, ten al menos auth (incluida) y rate limiting (no incluido aún).

## Estado

Listo para uso real. Probado en producción privada en `bbeat.howl.wtf`.

| Pieza | Estado |
|---|---|
| Reproductor con Media Session API (controles en lockscreen) | listo |
| Pantalla "Now Playing" full-screen con letras sincronizadas | listo |
| Ingesta Spotify (SpotifyScraper, sin Premium ni dev app) | listo |
| Ingesta YouTube y SoundCloud (yt-dlp directo) | listo |
| Multi-fuente con overrides de álbum/artista | listo |
| Auth con JWT + admin (registrar/banear/promover) | listo |
| Álbumes con dueño y visibilidad pública/privada | listo |
| Crear álbumes vacíos y añadirles pistas existentes con búsqueda | listo |
| Dedup automático (un track, varios álbumes vía M:N) | listo |
| Búsqueda en biblioteca + filtros mine/public/all | listo |
| Letras vía LRCLIB con sincronización en NowPlaying | listo |
| Subir ficheros locales (drag & drop multi-archivo) | listo |
| Editar/borrar pistas y álbumes desde UI | listo |
| Carátulas custom por álbum (re-embebe en todos los tracks) | listo |
| Stats dual (lo que ves tú vs total de la instancia) | listo |
| PWA instalable, audio en background | listo |
| Votify (descarga directa de Spotify) | requiere Premium (ver nota) |

## Stack

- **Backend**: FastAPI · SQLModel · SQLite · SpotifyScraper · Votify · yt-dlp · Mutagen · bcrypt · PyJWT
- **Frontend**: SvelteKit 5 · Tailwind 4 · TypeScript · Service Worker (PWA)
- **Audio**: FFmpeg
- **Empaquetado**: Docker (multi-stage) o systemd user-unit

## Self-hosting rápido

Requisitos: Python 3.12+, Node 22+, FFmpeg.

### Modo producción (recomendado)

```bash
git clone https://github.com/howlpy/bbeat.git
cd bbeat

# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend (build estático que sirve el backend)
cd ../frontend
npm install
npm run build

# Arrancar
cd ../backend
./venv/bin/python -m app.main
```

Abre `http://localhost:8787`. El primer usuario que se registra pasa a admin automáticamente y se le asignan los álbumes huérfanos.

### Como servicio systemd (sobrevive a reboots)

```ini
# ~/.config/systemd/user/bbeat.service
[Unit]
Description=Bbeat
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/bbeat/backend
ExecStart=%h/bbeat/backend/venv/bin/python -m app.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
loginctl enable-linger $USER          # sobrevive a logout
systemctl --user daemon-reload
systemctl --user enable --now bbeat
journalctl --user -u bbeat -f         # logs en vivo
```

### Docker

```bash
cp backend/.env.example backend/.env
docker compose up -d
```

## Configuración

Todas las variables viven en `backend/.env` (ver `.env.example`). Las más relevantes:

| Variable | Default | Notas |
|---|---|---|
| `BBEAT_HOST` / `BBEAT_PORT` | `0.0.0.0:8787` | Bind del servidor |
| `BBEAT_DEBUG` | `false` | `true` activa autoreload (no usar en prod) |
| `BBEAT_MUSIC_DIR` | `../data/music` | Dónde se guardan los .m4a/.mp3/.ogg |
| `BBEAT_DOWNLOAD_BACKEND` | `yt-dlp` | `yt-dlp` o `votify` (Votify requiere Premium en cookies) |
| `BBEAT_AUDIO_FORMAT` | `ogg` | `ogg`, `mp3` o `flac` (FLAC requiere Spotify Premium en cookies) |
| `BBEAT_MAX_CONCURRENT_JOBS` | `1` | Cuidado con la RAM si lo subes |

Los secretos (JWT key, cookies de Spotify) viven en `data/secrets/` con permisos `600`.

## Estructura

```
bbeat/
├── backend/                         FastAPI + worker de jobs
│   ├── app/
│   │   ├── api/                     endpoints HTTP
│   │   ├── services/                spotify, downloader, jobs, auth, access...
│   │   └── models.py                SQLModel (User, Track, Album, AlbumTrack, Job)
│   ├── requirements.txt
│   └── .env
├── frontend/                        SvelteKit
│   ├── src/
│   │   ├── routes/                  páginas
│   │   └── lib/                     api.ts, auth, player, jobs, componentes
│   └── package.json
├── data/                            (gitignored)
│   ├── music/                       biblioteca organizada por artista/álbum
│   ├── covers/                      carátulas extraídas
│   ├── secrets/                     jwt.key, spotify_cookies.txt
│   └── library.db                   SQLite
├── docker-compose.yml
└── Dockerfile
```

## Cómo funciona la ingesta

1. Pegas una URL en `/import`.
2. El frontend pide preview (`POST /api/ingest/preview`): SpotifyScraper o yt-dlp resuelven la metadata sin descargar.
3. Tú decides:
   - Nuevo álbum (puedes meter título/artista/año custom para no-Spotify).
   - Añadir a un álbum existente tuyo.
4. Confirmas; el backend crea Jobs en SQLite.
5. Un worker single-thread procesa la cola: descarga, FFmpeg para extraer audio, mutagen para tags + cover, scanner para indexar.
6. Si el track ya existe en la biblioteca (mismo ID externo), no descarga: añade el track a tu álbum vía `album_tracks` (M:N).

## Votify: solo con Spotify Premium

El pipeline Votify+librespot funciona correctamente (auth, fetch de metadata, fetch del stream cifrado). Pero a finales de 2025 Spotify **bloqueó la entrega de "audio keys" (las claves AES para descifrar el stream) a cuentas Free**. Sin esa clave los bytes son inútiles. El error típico es `RuntimeError: Failed fetching audio key!`.

Esto afecta a TODO el ecosistema librespot (Votify, Zotify, etc.), no es específico de Bbeat. Con una cuenta Premium activa funciona; con Free no hay workaround técnico.

Por defecto Bbeat queda configurado con **yt-dlp** como primario. Si tienes Premium, sube las cookies en `/settings` y cambia `BBEAT_DOWNLOAD_BACKEND=votify` en el `.env`. Calidad real:

| Backend | Formato | Bitrate aprox |
|---|---|---|
| yt-dlp (YouTube Music) | m4a (AAC) | 128–256 kbps |
| Votify con Premium Standard | Ogg Vorbis | 160 kbps |
| Votify con Premium High | Ogg Vorbis | 320 kbps |

Para uso normal en auriculares/altavoces no audiophile, la diferencia es imperceptible.

## Por qué no usamos la API pública de Spotify

Desde noviembre 2024, Spotify exige Premium en la cuenta dueña del developer app para llamar a cualquier endpoint, incluso `search`. Bbeat usa **SpotifyScraper** (scraping de `open.spotify.com`) para obtener metadata sin credenciales. El audio viene de yt-dlp (YouTube Music como fuente) o, si tienes Premium, de Votify (sesión privada con cookies).

## Exponer Bbeat a internet (opcional)

Si quieres que tus colegas puedan usarlo desde fuera de tu LAN, lo más simple:

1. **DNS**: en tu proveedor (ej. Cloudflare), un record `A` apuntando a tu IP pública con proxy activado (nube naranja).
2. **Router**: port forward `WAN 80 → LAN <ip-server>:8787` (en modo Cloudflare Flexible, CF habla HTTP al origen por el puerto 80).
3. **Cloudflare → SSL/TLS**: modo **Flexible** + Always Use HTTPS activado.

Bbeat ya trae auth: el primer usuario registrado es admin auto y desde `/admin` puedes banear o promover cuentas. Tus amigos se registran ellos mismos. Para mayor seguridad considera **Cloudflare Tunnel + Access** (ningún puerto abierto en tu router, magic-link por email).

## Roadmap

- Importar playlists locales (M3U)
- Múltiples cookies de Spotify (una por usuario, para que cada uno use su Premium)
- Rate limiting + protección DDoS para instancias públicas
- Soporte de Subsonic API (compatibilidad con clientes como Symfonium / DSub)
- Historial de reproducción + recomendaciones tipo "más escuchadas"
- Mover pistas entre álbumes en bulk (drag&drop o multi-select)
- Importar listas de Apple Music / Deezer / YouTube playlists

## Licencia

MIT. Ver [LICENSE](./LICENSE).

El uso del software es bajo tu responsabilidad: cumplir con los ToS de cada plataforma y la legislación de copyright es cosa del operador.
