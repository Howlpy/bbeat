# Plan: rellenar el género de toda la biblioteca

Objetivo final: poder preguntar *"¿cuáles son las 10 canciones de rap más
escuchadas esta semana en el server?"* y que salga sola una playlist.

Estado al escribir esto (30-08-2026): **17 de 1830 pistas tienen género**.
Todo lo demás está vacío. Se rellena solo si el fichero traía tag, o a mano
desde el diálogo de editar.

---

## 1. La trampa que hay que esquivar primero

`scanner._index_one()` reconstruye la fila de la pista en **cada** escaneo, y
entre los campos que pisa está el género:

```python
fields = {..., "genre": tags["genre"], ...}   # scanner.py:299
for k, v in fields.items():
    if getattr(track, k) != v:
        setattr(track, k, v)                  # None incluido
```

No hay salto por mtime: el bucle pasa por los 1830 ficheros siempre. Así que
**cualquier género escrito solo en la base de datos lo borra el siguiente
escaneo de la biblioteca.** Esto invalida el enfoque obvio (un UPDATE masivo
sobre `tracks.genre`) y es la razón de la decisión que viene ahora.

## 2. Decisión de diseño: el género va en el ARTISTA

Se añade `Artist.genre`. `Track.genre` se queda como está.

| Campo | Quién lo escribe | Para qué |
|---|---|---|
| `Artist.genre` | el backfill automático | el género de referencia |
| `Track.genre` | el tag del fichero, o el usuario a mano | excepción puntual |

La API resuelve `track.genre or artist.genre`. Ventajas:

- El escáner **nunca toca `artists`**, así que el problema del apartado 1
  desaparece sin tener que reescribir los tags de 1830 ficheros.
- 631 artistas contra 1830 pistas: un tercio del trabajo y un tercio de las
  peticiones.
- Corregir un artista arregla todas sus canciones de golpe.
- El caso raro (un disco de un rapero que en realidad es flamenco) se sigue
  pudiendo cubrir a mano en la pista, y esa gana.

Aparte, arreglar el escáner para que un tag ausente **no** borre un género que
ya existe en la BD. Es un bug con o sin este plan.

## 3. De dónde sale el género: Deezer

Probado contra artistas reales de la biblioteca. Resultados medidos, no
suposiciones:

| Fuente | Resultado |
|---|---|
| **Deezer** | sin API key, 18/18 artistas encontrados, rap español perfecto |
| MusicBrainz | 503 por rate limit, y `genres` vacío en casi todo el rap español |
| Spotify Web API | bbeat usa SpotifyScraper, no la Web API: haría falta registrar una app |
| Last.fm | buena cobertura de tags, pero pide API key. Plan B |

Deezer no da género del artista, solo del álbum. Se resuelve por **votación**:
se piden hasta 6 álbumes del artista y gana el género más repetido.

### Reglas de aceptación

```
acepta si:  nombre normalizado idéntico al de Deezer
       y    el ganador tiene >= 2 votos
       y    >= 50 % de los votos
si no:      a la cola de revisión, sin escribir nada
```

Medido sobre 25 artistas aleatorios (incluida la cola larga, que es la
difícil): **60 % automático, 28 % a revisar, 12 % descartado por nombre**.
De los aceptados, ninguno estaba mal.

Las tres reglas no son adorno, cada una atrapó un fallo real:

- `Alok` → Deezer devolvió `Alok (IN)`, **otro artista**. Lo para el nombre.
- `til i collapse` (un nombre basura que vino de YouTube) → `Till I Collapse`.
  Lo para el nombre.
- `Powerwolf` → `Clásica` al 100 %… con **un solo voto**, de un disco
  sinfónico. Lo para el mínimo de votos. Sin esa regla, entra mal.
- `Anthrax` → `Alternativo` al 40 %. Lo para el umbral de confianza.

### Pendiente de resolver

- Nombres de colaboración: `Los Chikos del Maíz & El Hombre Viento` no existe
  en Deezer. Hay que partir por `&`, `feat`, `,` y quedarse con el primero.
- `Various Artists` y `Unknown Artist` (118 pistas) no tienen artista real: o
  se dejan sin género, o se resuelven pista a pista.

## 4. Taxonomía propia

Los nombres de Deezer no valen tal cual para el objetivo: `Rap/Hip Hop`,
`Electro`, `Techno/House` y `Dance` son cuatro etiquetas para dos ideas. Hace
falta una tabla de mapeo a un vocabulario cerrado de bbeat:

```
rap          <- Rap/Hip Hop, Hip Hop
reggaeton    <- Reggaeton, Latino urbano
latino       <- Latino, Flamenco, Salsa
electronica  <- Electro, Dance, Techno/House, Drum & Bass
rock         <- Rock, Hard Rock, Alternativo, Indie Pop/Rock
metal        <- Metal, Metal Extremo
pop          <- Pop
otros        <- lo que no encaje
```

Sin esto, "top de rap" tendría que buscar por varias cadenas distintas y se
rompería en cuanto Deezer cambie una etiqueta. **El vocabulario cerrado es lo
que hace posible la playlist semanal**, no un detalle de limpieza.

## 5. Trabajo, en orden

1. `Artist.genre` + migración (tabla nueva no, columna: va en `columns_to_add`).
2. Arreglar el pisado del escáner.
3. `backend/scripts/backfill_genres.py`:
   - `--dry-run` por defecto, que escriba un informe y no toque nada.
   - Reanudable: solo mira artistas con `genre IS NULL`.
   - Una petición cada ~150 ms. 631 artistas ≈ 20-25 min de reloj.
   - Deja en un fichero aparte la cola de revisión.
4. La API devuelve `track.genre or artist.genre`; el frontend ya sabe pintar
   género (`showGenre` en `TrackList`).
5. Editar el género de un artista desde la UI (para la cola de revisión).
6. Playlists semanales: `plays` de los últimos 7 días, agrupado por género.

## 6. Ojo con esto al llegar al punto 6

`my_stats` y el resto de agregados usan **UTC**, no hora de Madrid
(`func.date(Play.played_at)`, `datetime.utcnow()`). Una "semana" calculada así
empieza y acaba dos horas antes de lo que la gente espera, y lo escuchado
entre las 00:00 y las 02:00 cae en el día anterior. Conviene decidir la zona
antes de construir nada encima.
