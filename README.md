# Bbeat

Servidor de música personal self-hosted. Webapp responsive mobile-first (+ app nativa de Android) que descarga música automáticamente desde URLs públicas y la sirve a tus dispositivos.

Pegas una URL de Spotify, YouTube o SoundCloud y Bbeat extrae la metadata, descarga el audio, lo etiqueta y organiza (`Artista/Álbum/NN - Título.ext`), lo indexa y lo deja listo para reproducir. Si la pista ya existe no la vuelve a bajar (detecta el duplicado por ID de origen y, si el ID no casa, por título + artista + duración): solo la enlaza al destino que elijas.

Pensado para uso personal o entre amigos en una instancia compartida: cada usuario tiene sus favoritos, su historial y su "Wrapped", y puede **descargar canciones para escucharlas sin conexión**. Además habla la **API Subsonic**, así que puedes escuchar tu música desde cualquier cliente compatible (ideal para iPhone: Amperfy, play:Sub, substreamer… o Symfonium en cualquier plataforma).

> Aviso: exponer Bbeat a internet es bajo tu responsabilidad (ToS de las plataformas, copyright). Trae auth, pero el rate limiting aún no está incluido.

## Estado

Listo para uso real, probado en producción.

| Pieza | Estado |
|---|---|
| **App nativa de Android** (Capacitor): offline real a disco, segundo plano, multi-servidor | listo |
| **API Subsonic**: navegar, buscar, reproducir, crear/editar playlists, favoritos y scrobble desde clientes de terceros (iPhone, etc.) | listo |
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
| `BBEAT_MAX_CONCURRENT_JOBS` | `1` | Descargas en paralelo (ojo con la RAM en hosts pequeños) |
| `BBEAT_TRANSCODE_CONCURRENCY` | `2` | Procesos ffmpeg simultáneos de transcoding Subsonic (limita pico de CPU) |
| `BBEAT_TRANSCACHE_MAX_MB` | `1024` | Tope en disco de la cache de transcoding; al superarlo purga los menos usados (0 = sin límite) |
| `BBEAT_CORS_ORIGINS` | `http://localhost:5173` | Orígenes extra; los del WebView nativo se permiten siempre |

Los secretos (JWT key, cookies opcionales de Spotify) viven en `data/secrets/` con permisos `600`. La carpeta `data/` está fuera de git.

## Cómo funciona

1. Pegas una URL en `/import`; el backend resuelve la metadata sin descargar (SpotifyScraper o yt-dlp) y muestra un preview.
2. Eliges el destino: **auto** (canción suelta / su álbum / colección multi-artista según el tipo), **nuevo** o **añadir a uno tuyo**; en playlists puedes (des)marcar pistas.
3. Un worker procesa la cola: busca en YouTube el mejor match (con scoring que penaliza reacciones, directos y vídeos sin relación), descarga el audio en **Opus**, etiqueta, embebe carátula e indexa.

El audio viene de YouTube v?a yt-dlp; se prefiere el stream Opus y se copia sin recodificar.

> No usamos la API pública de Spotify porque desde nov-2024 exige Premium en el dev app hasta para `search`; SpotifyScraper cubre la metadata sin credenciales.

## Clientes Subsonic (iPhone y demás)

Bbeat implementa la [API Subsonic](http://www.subsonic.org/pages/api.jsp), el estándar de facto de los servidores de música self-hosted. Sirve para escuchar desde apps de terceros — útil sobre todo en iPhone, donde no hay app nativa de Bbeat.

1. En **Ajustes → Acceso Subsonic**, genera tu **token** (es un secreto aparte de tu contraseña).
2. En el cliente, añade un servidor con la **URL** de tu instancia, tu **usuario** y el **token como contraseña**.

Clientes recomendados: **Amperfy**, **play:Sub** o **substreamer** (iOS); **Symfonium**, **Tempo** o **DSub** (Android); **Sonixd** / **Feishin** (escritorio). Funciona el browsing por artistas/álbumes/canciones, búsqueda, crear/editar/borrar playlists, favoritos (estrella ↔ "me gusta") y scrobble (alimenta tu historial y Wrapped).

> Las playlists creadas desde un cliente Subsonic son las mismas que ves en la app de Bbeat (colecciones multi-artista). Borrar una playlist solo elimina la lista, **nunca los ficheros de audio**. Solo puedes editar/borrar las playlists de las que eres dueño.

> Por qué un token y no tu contraseña: Subsonic exige poder validar `md5(contraseña+salt)`, pero Bbeat guarda las contraseñas con bcrypt (irreversible). El token dedicado es regenerable y revocable desde Ajustes en cualquier momento.

> Transcoding: por defecto el stream sirve el Opus tal cual. Si un cliente pide otro formato (`format=mp3|aac|ogg`), Bbeat transcodifica on-the-fly con FFmpeg y cachea el resultado en disco. El nº de procesos ffmpeg y el tamaño de la cache se ajustan con `BBEAT_TRANSCODE_CONCURRENCY` y `BBEAT_TRANSCACHE_MAX_MB`.

## Géneros con IA (opcional)

El género de cada pista sale de una cascada de fuentes (Last.fm, Deezer, iTunes, Wikidata). Acierta en los artistas grandes, pero a veces etiqueta mal a un artista entero. Esta función, **desactivada por defecto**, usa un LLM (el que tú elijas, sin dependencias de ningún proveedor) para revisarlos **por artista**:

- Al modelo le llegan las pistas del artista, sus géneros actuales y (si lo configuras) fragmentos de una búsqueda web. Elige uno de los géneros de la lista cerrada de Bbeat, o `unknown` si no está seguro, y solo marca excepciones por pista con evidencia clara.
- Solo se aplica con confianza ≥ `BBEAT_AI_MIN_CONFIDENCE` (0.75). Lo demás va a **Admin → Géneros con IA → Revisar sugerencias** para aceptar, rechazar o cambiar el género.
- Una pista cuyo género edites a mano (o un artista entero desde su página, solo admin) queda **bloqueada**: ni la IA ni `backfill_genres` la vuelven a tocar.
- Las pasadas son reanudables: si el proveedor agota la cuota (429), se para limpiamente; relanza más tarde y continúa con los artistas pendientes.
- Aparte, y **sin necesitar IA**, al importar una pista cuyo género discrepa del de su artista (≥3 pistas y ≥80 % de acuerdo) se conserva el del artista (`BBEAT_ARTIST_CONSISTENCY`). Con IA activa, los casos desconocidos o discutidos se encolan en segundo plano.

Variables (todas opcionales, en `backend/.env`):

| Variable | Default | Notas |
|---|---|---|
| `BBEAT_AI_PROVIDER` | `none` | `openai` · `gemini` · `anthropic` · `ollama` · `none` |
| `BBEAT_AI_API_KEY` | | Clave del proveedor (no hace falta en Ollama/LM Studio locales) |
| `BBEAT_AI_MODEL` | según proveedor | Gemini: `gemini-2.5-flash-lite` · OpenAI: `gpt-4o-mini` · Anthropic: `claude-haiku-4-5` · Ollama: `llama3.2` |
| `BBEAT_AI_BASE_URL` | según proveedor | Para cualquier servidor compatible con la API de OpenAI (usa `openai` como proveedor) |
| `BBEAT_AI_RPM` | `10` | Peticiones por minuto; sube o baja según tu cuota |
| `BBEAT_AI_TIMEOUT` | `60` | Segundos por petición |
| `BBEAT_AI_MIN_CONFIDENCE` | `0.75` | Umbral para aplicar sin revisión |
| `BBEAT_AI_BATCH_ARTISTS` | `5` | Artistas pequeños (≤10 pistas) que comparten petición, para ahorrar cuota |
| `BBEAT_SEARCH_PROVIDER` | `none` | `searxng` · `none` (evidencia web; mejora mucho a artistas poco conocidos) |
| `BBEAT_SEARXNG_URL` | | Ej. `http://localhost:8080` (necesita el formato JSON activado en SearXNG) |
| `BBEAT_ARTIST_CONSISTENCY` | `true` | Coherencia por artista al importar |

Ejemplos de `backend/.env`:

```ini
# Google Gemini (clave gratuita en https://aistudio.google.com/apikey; cuota diaria baja)
BBEAT_AI_PROVIDER=gemini
BBEAT_AI_API_KEY=AIza...

# OpenRouter (o Groq, Together, Mistral, DeepSeek, LM Studio, vLLM...: cualquier API compatible con OpenAI)
BBEAT_AI_PROVIDER=openai
BBEAT_AI_BASE_URL=https://openrouter.ai/api/v1
BBEAT_AI_API_KEY=sk-or-...
BBEAT_AI_MODEL=meta-llama/llama-3.3-70b-instruct
# Groq: BBEAT_AI_BASE_URL=https://api.groq.com/openai/v1

# Ollama local (sin clave)
BBEAT_AI_PROVIDER=ollama
BBEAT_AI_MODEL=llama3.1:8b

# Anthropic
BBEAT_AI_PROVIDER=anthropic
BBEAT_AI_API_KEY=sk-ant-...

# OpenAI
BBEAT_AI_PROVIDER=openai
BBEAT_AI_API_KEY=sk-...

# Búsqueda web con tu SearXNG (opcional, combina con cualquiera de los anteriores)
BBEAT_SEARCH_PROVIDER=searxng
BBEAT_SEARXNG_URL=http://localhost:8080
```

Desde la línea de comandos (`cd backend`; con Docker: `docker compose exec bbeat python -m scripts.ai_genres ...`):

```bash
python -m scripts.ai_genres --limit 20 --report informe.csv   # simulacro: no escribe nada
python -m scripts.ai_genres --apply --limit 100               # aplica y encola lo dudoso
python -m scripts.ai_genres --apply --only-missing            # solo artistas con pistas sin género
python -m scripts.ai_genres --artist "Maná" --force --apply   # reclasifica un artista
```

`--suspicious` limita a artistas sin género, con géneros mezclados o con 1–2 pistas. El simulacro no guarda progreso (gasta cuota cada vez); `--apply` sí es reanudable.

## Exponer a internet (opcional)

Lo más simple es ponerlo detrás de **Cloudflare**: un record `A` a tu IP con proxy activado, port forward del router al puerto del backend, y SSL/TLS en modo Flexible + Always Use HTTPS. Para mayor seguridad, **Cloudflare Tunnel + Access** (sin abrir puertos). Recuerda que el rate limiting aún no está incluido.

## Roadmap

- Cola persistente (sobrevive al cierre, con posición)
- Editar/mover pistas en bulk · importar de Apple Music / Deezer

## Licencia

MIT. Ver [LICENSE](./LICENSE). El uso es bajo tu responsabilidad: cumplir los ToS de cada plataforma y la legislación de copyright es cosa del operador.
