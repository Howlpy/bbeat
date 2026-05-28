# Bbeat

Servidor de música personal self-hosted. Webapp responsive mobile-first (+ app nativa de Android) que descarga música automáticamente desde URLs públicas y la sirve a tus dispositivos.

Pegas una URL de Spotify, YouTube o SoundCloud y Bbeat extrae la metadata, descarga el audio, lo etiqueta y organiza (`Artista/Álbum/NN - Título.ext`), lo indexa y lo deja listo para reproducir. Si la pista ya existe no la vuelve a bajar (detecta el duplicado por ID de origen y, si el ID no casa, por título + artista + duración): solo la enlaza al destino que elijas.

Pensado para uso personal o entre amigos en una instancia compartida: cada usuario tiene sus favoritos, su historial y su "Wrapped", y puede **descargar canciones para escucharlas sin conexión**.

> Aviso: exponer Bbeat a internet es bajo tu responsabilidad (ToS de las plataformas, copyright). Trae auth, pero el rate limiting aún no está incluido.

## Estado

Listo para uso real, probado en producción.

| Pieza | Estado |
|---|---|
| **App nativa de Android** (Capacitor): offline real a disco, segundo plano, multi-servidor | listo |
| Reproductor con Media Session (controles en lockscreen), cola, shuffle/repeat | listo |
| "Now Playing" full-screen con color de la portada + letras sincronizadas (LRCLIB) | listo |
| Favoritos, historial, "más escuchadas" y **Wrapped** | listo |
| **Descargas offline** (PWA en IndexedDB / app nativa a disco) | listo |
| Audio en **Opus** (copia del stream sin recodificar: mínimo tamaño, máxima calidad) | listo |
| Carátula propia por pista (con miniatura de YouTube de fallback) | listo |
| Pool global: cualquier usuario ve y reproduce todo el catálogo | listo |
| Ingesta Spotify / YouTube / SoundCloud + playlists y mixes (con deselección) | listo |
| Playlists multi-artista (una colección "Various Artists", no N álbumes) | listo |
| Biblioteca por "guardados" (Guardados / Explorar), álbumes con dueño | listo |
| Auth JWT + admin (registrar/banear/promover) · dedup por ID externo + título/artista/duración | listo |
| Subir ficheros locales, editar/borrar pistas y álbumes desde la UI | listo |

> **Pool global:** Pistas, álbumes, búsqueda y streaming son compartidos — cualquier usuario autenticado ve y reproduce todo el catálogo de la instancia. Lo que define tu biblioteca personal es **guardar**; el dueño de un álbum solo controla quién puede editarlo. Pensado para instancias entre gente de confianza.

## Stack

- **Backend**: FastAPI · SQLModel · SQLite · SpotifyScraper · yt-dlp · Mutagen · bcrypt · PyJWT · FFmpeg
- **Frontend**: SvelteKit 5 · Tailwind 4 · TypeScript · PWA (Service Worker)
- **App Android**: Capacitor (envuelve el mismo frontend) — ver [ANDROID.md](./ANDROID.md)

## Self-hosting

Requisitos: Python 3.12+, Node 22+, FFmpeg.

1. **Backend**: crea un venv e instala `backend/requirements.txt`; copia `backend/.env.example` → `backend/.env`.
2. **Frontend**: `cd frontend && npm install && npm run build` (el backend sirve ese build estático).
3. **Arranca**: `python -m app.main` desde `backend/` y abre `http://localhost:8787`.

El primer usuario que se registra pasa a admin automáticamente.

Para producción, como servicio **systemd** (con `loginctl enable-linger` para sobrevivir a reboots) o con **Docker** (`docker compose up -d`). La app de Android se compila aparte — ver [ANDROID.md](./ANDROID.md).

## Configuración

Todo en `backend/.env` (ver `.env.example`). Lo más relevante:

| Variable | Default | Notas |
|---|---|---|
| `BBEAT_HOST` / `BBEAT_PORT` | `0.0.0.0:8787` | Bind del servidor |
| `BBEAT_DEBUG` | `false` | `true` = autoreload (no usar en prod) |
| `BBEAT_MUSIC_DIR` | `../data/music` | Dónde se guarda la biblioteca |
| `BBEAT_AUDIO_FORMAT` | `opus` | Formato de descarga (opus = copia del stream Opus, sin recodificar) |
| `BBEAT_CORS_ORIGINS` | `http://localhost:5173` | Orígenes extra; los del WebView nativo se permiten siempre |

Los secretos (JWT key, cookies opcionales de Spotify) viven en `data/secrets/` con permisos `600`. La carpeta `data/` está fuera de git.

## Cómo funciona

1. Pegas una URL en `/import`; el backend resuelve la metadata sin descargar (SpotifyScraper o yt-dlp) y muestra un preview.
2. Eliges el destino: **auto** (canción suelta / su álbum / colección multi-artista según el tipo), **nuevo** o **añadir a uno tuyo**; en playlists puedes (des)marcar pistas.
3. Un worker procesa la cola: busca en YouTube el mejor match (con scoring que penaliza reacciones, directos y vídeos sin relación), descarga el audio en **Opus**, etiqueta, embebe carátula e indexa.

El audio viene de YouTube vía yt-dlp (se prefiere el stream Opus y se copia sin recodificar). Opcionalmente, con cookies de Spotify Premium en `/settings`, puede usar Votify (Ogg Vorbis) — pero Spotify bloquea las audio keys a cuentas Free, así que yt-dlp es el camino por defecto.

> No usamos la API pública de Spotify porque desde nov-2024 exige Premium en el dev app hasta para `search`; SpotifyScraper cubre la metadata sin credenciales.

## Exponer a internet (opcional)

Lo más simple es ponerlo detrás de **Cloudflare**: un record `A` a tu IP con proxy activado, port forward del router al puerto del backend, y SSL/TLS en modo Flexible + Always Use HTTPS. Para mayor seguridad, **Cloudflare Tunnel + Access** (sin abrir puertos). Recuerda que el rate limiting aún no está incluido.

## Roadmap

- Rate limiting + protección anti-abuso para instancias públicas
- Cola persistente (sobrevive al cierre, con posición)
- Soporte Subsonic API (clientes tipo Symfonium / DSub)
- Editar/mover pistas en bulk · importar de Apple Music / Deezer

## Licencia

MIT. Ver [LICENSE](./LICENSE). El uso es bajo tu responsabilidad: cumplir los ToS de cada plataforma y la legislación de copyright es cosa del operador.
