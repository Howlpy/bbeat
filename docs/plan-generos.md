# Plan: rellenar el género de toda la biblioteca

Objetivo final: poder preguntar *"¿cuáles son las 10 canciones de rap más
escuchadas esta semana en el server?"* y que salga sola una playlist.

Estado al escribir esto (30-08-2026): **17 de 1830 pistas tienen género**.
Todo lo demás está vacío. Se rellena solo si el fichero traía tag, o a mano
desde el diálogo de editar.

---

## 1. El género va en la PISTA

Una canción tiene un género; un artista, no necesariamente. Kase.O tiene discos
de rap y colaboraciones de jazz; un rapero puede sacar un disco de flamenco.
Colgar el género del artista obliga a mentir justo en los casos que uno querría
acertar.

Así que el género vive en `Track.genre`, que **ya existe**. No hace falta
columna nueva ni migración.

### Lo que esto arregla de paso

`scanner._index_one()` reconstruye la fila de la pista en cada escaneo, género
incluido, y no hay salto por mtime: pasa por los 1830 ficheros siempre.

```python
fields = {..., "genre": tags["genre"], ...}   # scanner.py:299
```

Con el género en la pista eso deja de ser un problema y pasa a ser lo correcto,
**siempre que escribamos el tag en el fichero**. El tag es la fuente de la
verdad, igual que para el título o el artista; la BD es un índice de lo que hay
en disco. El escáner no pisa nada: lee lo que nosotros pusimos.

Y la maquinaria ya está montada — `organizer.write_tags()` escribe `meta.genre`
desde hace tiempo:

```python
if meta.genre is not None:              # organizer.py:155
    genre = meta.genre.strip()
    if genre: audio["genre"] = genre
```

Lo único que pasa es que **nadie rellena nunca `meta.genre`**. Ahí está el
agujero, y es de una línea.

## 2. De dónde sale el género

Probado contra pistas reales de la biblioteca, no supuesto.

| Fuente | Resultado |
|---|---|
| **Deezer** | sin API key, cubre el 80 % por pista, rap español perfecto |
| MusicBrainz | 503 por rate limit, y `genres` vacío en casi todo el rap español |
| Spotify | usan SpotifyScraper, que **no devuelve género ni ISRC** (ver §3) |
| Last.fm | tags por pista de verdad, pero pide API key. Plan B si Deezer flojea |

Deezer no expone género de pista: lo expone del **álbum**. Así que la pista se
busca por artista + título y hereda el género de *su* álbum — que es distinto,
y mejor, que el del artista.

### La cascada, con los números que la justifican

Sobre 30 pistas al azar de la biblioteca:

| | pistas |
|---|---|
| por pista y por artista coinciden | 16 |
| **difieren** (y gana la pista, 3 de 3) | 3 |
| solo lo resuelve la **pista** | 5 |
| solo lo resuelve el **artista** | 3 |
| ninguno de los dos | 3 |

- **Por pista: 24/30 = 80 %.**
- **Cascada pista → artista: 27/30 = 90 %.**

Los tres casos en que difieren dan la razón al enfoque por pista:

| pista | por pista | por artista |
|---|---|---|
| `dnb demon — Can't Get You Out Of My Head (DnB Mix)` | Electro | Dance |
| `blurr. — TOO SWEET (Dnb)` | Dance | Electro |
| `Bow Wow — That's My Name` | Pop | **Música asiática** |

El tercero es el importante: por artista, Deezer devolvió otro Bow Wow y le
habría colgado "Música asiática" a **todas** sus canciones. Por pista, el álbum
correcto lo corrige. Un fallo a nivel de artista contamina la discografía
entera; a nivel de pista se queda en una canción.

Los 5 que solo resuelve la pista son artistas de la cola larga (Kaze, FUFU,
Plex, Beny Jr, Oxidaksi) con pocos discos en Deezer: no hay votos suficientes
para decidir el artista, pero el álbum concreto sí tiene género.

### El artista sigue haciendo falta, como respaldo

Los 3 que solo resuelve el artista fallan por el **título**, no por el género:
`Diamonds On Me`, `Potato Salad`, `ONDE MI (Vídeo Oficial)`. Los títulos de
bbeat arrastran restos de YouTube y Spotify (`- Remix`, `- Remaster 2015`,
`(Vídeo Oficial)`, `feat …`).

**Limpiar el título antes de buscar no es cosmético, es lo que sube la
cobertura.** Y `downloader.py` ya tiene esa normalización resuelta
(`_norm_text`, `TITLE_NOISE_WORDS`, `_title_core`): hay que reutilizarla, no
escribir otra que se desincronice.

### Reglas de aceptación

Por pista:

```
acepta si el artista del resultado de Deezer coincide (normalizado)
         y su álbum trae al menos un género
```

Por artista (respaldo), medido sobre 25 artistas al azar:

```
acepta si nombre normalizado idéntico
       y el género ganador tiene >= 2 votos de álbum
       y >= 50 % de los votos
```

Las tres reglas del respaldo no son adorno, cada una paró un fallo real:

- `Alok` → Deezer devolvía `Alok (IN)`, **otro artista**. Lo para el nombre.
- `til i collapse` (nombre basura venido de YouTube) → `Till I Collapse`. Nombre.
- `Powerwolf` → `Clásica` al 100 %… con **un solo voto**, de un disco
  sinfónico. Lo para el mínimo de votos.
- `Anthrax` → `Alternativo` al 40 %. Lo para el umbral de confianza.

## 3. La vía exacta está cerrada (por ahora)

Deezer permite buscar por ISRC, que sería una coincidencia exacta sin depender
de cómo esté escrito el título:

```
GET https://api.deezer.com/track/isrc:GBAAM8500002
  -> Joan Armatrading / One Night / generos: ['Pop']       ✔ funciona
```

Pero bbeat no tiene ISRC que darle. Comprobado: `SpotifyClient.get_track()`
devuelve `album, artists, duration_ms, explicit, id, images, name, play_count,
playable, preview_url, release_date, share_url, track_number, uri`. **No hay
`isrc` ni `external_ids`.**

Por tanto `isrc=item.get("isrc")` en `spotify.py:122` es código muerto que
siempre da `None`, y las otras dos rutas (`_track_from_playlist_item`,
`_track_meta_from_track_endpoint`) ya ponen `None` a mano. Casi toda la
biblioteca entró por playlist, o sea por la ruta que ni lo mira.

Queda anotado: **si algún día se registra una app en la Web API de Spotify**,
`external_ids.isrc` desbloquea la búsqueda exacta y esto pasa de ~90 % a casi
100 % sin tocar nada más. No es motivo para hacerlo ahora.

## 4. Taxonomía propia

Los nombres de Deezer no valen tal cual: `Rap/Hip Hop`, `Electro`,
`Techno/House` y `Dance` son cuatro etiquetas para dos ideas. Hace falta mapear
a un vocabulario cerrado:

```
rap          <- Rap/Hip Hop, Hip Hop
reggaeton    <- Reggaeton
latino       <- Latino, Flamenco, Salsa
electronica  <- Electro, Dance, Techno/House, Drum & Bass
rock         <- Rock, Hard Rock, Alternativo, Indie Pop/Rock
metal        <- Metal, Metal Extremo
pop          <- Pop
otros        <- lo que no encaje
```

**Esto es lo que hace posible la playlist semanal**, no una limpieza estética:
sin vocabulario cerrado, "top de rap" tendría que buscar varias cadenas y se
rompería en cuanto Deezer renombre una etiqueta.

Decisión pendiente: si el tag del fichero guarda la etiqueta canónica (`rap`) o
la original (`Rap/Hip Hop`). Propuesta: **la canónica**, para que el tag y las
consultas hablen el mismo idioma y un reescaneo no reintroduzca variantes.

## 5. Trabajo, en orden

### a) Servicio de resolución

`backend/app/services/genres.py`:

- `resolve(meta) -> Optional[str]`: pista → artista → `None`.
- Caché de géneros por álbum y por artista. En el backfill se repiten mucho:
  las 30 pistas de la prueba necesitaron bastantes menos consultas de álbum que
  de pista.
- Espaciado ~150 ms. El límite público de Deezer ronda 50 peticiones / 5 s; con
  ese espaciado las pruebas nunca lo tocaron.
- Un fallo de red devuelve `None`, nunca una excepción que tumbe una descarga.

### b) Ingesta: que las nuevas ya entren con género

Una línea en `jobs.py:556`, justo antes de organizar:

```python
meta.genre = meta.genre or genres_svc.resolve(meta)
final_path = organizer.organize(dl_result.file_path, meta)
```

Va en el worker y no al crear el job: una playlist de 200 canciones haría 200
consultas dentro de la petición HTTP. En el worker se reparte, y un fallo no
rompe la descarga.

### c) Backfill de las 1830 que ya están

`backend/scripts/backfill_genres.py`:

- `--dry-run` por defecto: informe y no toca nada.
- **Solo rellena donde `genre IS NULL`.** Así una corrección a mano nunca se
  pisa al reejecutar, y no hace falta una columna `genre_source`.
- Escribe el tag con mutagen **y** actualiza la BD, en ese orden. Si solo se
  escribiera la BD, el siguiente escaneo lo borraría (§1).
- Reanudable, y deja aparte la lista de lo que no pudo resolver.
- ~1830 consultas de pista más los álbumes cacheados ≈ 10-15 min.

### d) UI

`TrackList` ya sabe pintar género (`showGenre`) y ya se puede ordenar por
género con el selector nuevo. Falta poder editar el género en lote, para
despachar la cola de revisión de una sentada.

### e) Playlists semanales

`plays` de los últimos 7 días, unido a `tracks`, agrupado por género canónico.

## 6. Ojo con esto al llegar al punto (e)

`my_stats` y los agregados usan **UTC**, no hora de Madrid
(`func.date(Play.played_at)`, `datetime.utcnow()`). Una "semana" calculada así
empieza y acaba dos horas antes de lo que la gente espera, y lo escuchado entre
las 00:00 y las 02:00 cae en el día anterior. Conviene decidir la zona antes de
construir nada encima.
