# Genre detection

Bbeat stores a genre **per track** (`Track.genre`), not per artist: one artist can have albums in different genres, and an artist-level genre would be wrong exactly where it matters. The tag is written to the audio file (mutagen) and the database is an index of what is on disk, so a rescan does not undo it.

## Sources and voting

Genres come from a cascade of sources: Last.fm (needs `BBEAT_LASTFM_API_KEY`), Deezer, iTunes and Wikidata. The result is decided by **consensus between sources** rather than the first source that answers. Labels are mapped to a closed, canonical vocabulary (for example Deezer's `Rap/Hip Hop` and `Hip Hop` both become `rap`), which is what makes queries such as the weekly genre charts reliable.

Safeguards that exist because they prevented real mistakes:

- Titles are cleaned of YouTube/Spotify noise (`- Remix`, `(Official Video)`, `feat ...`) before searching.
- Artist names must match after normalization, to avoid homonymous artists.
- An artist-level result needs enough votes and agreement before it can override a track's genre.
- Generic artists such as "Various Artists" are not searched in catalogs.

## Artist consistency

On import, if a track's genre disagrees with its artist's established genre (at least 3 tracks and at least 80% agreement), the artist's genre is kept. This works without AI and can be disabled with `BBEAT_ARTIST_CONSISTENCY=false`.

## Editing and locking

You can edit a track's genre from its edit dialog, and an artist's genre from the artist page (admin only). Manual edits are locked and are not overwritten by automatic detection, the AI classifier or the backfill script.

## Optional AI classifier

For artists the cascade gets wrong, an optional LLM pass with a review queue in Admin. See [ai-genres.md](./ai-genres.md).

## Scripts

Run from `backend/`.

```bash
python -m scripts.backfill_genres --json report.json   # dry run by default
python -m scripts.backfill_genres --apply              # fills tracks without a genre
python -m scripts.ai_genres --limit 20                 # AI pass, dry run by default
```

By default `backfill_genres` only touches tracks with no genre, and it never touches locked tracks, so rerunning it does not overwrite manual corrections. Pass `--reprocesar` (the flag keeps its Spanish name) to re-resolve the whole library after the cascade improves (it only writes when the result changes). `--limit N` and `--no-artist-fallback` are also available.

## Notes

- `docs/plan-generos.md` is the original design note (in Spanish) written while the cascade was being built. Its numbers and "pending work" section are historical; this page describes the current behavior.
- Weekly charts use a rolling 7-day window computed in UTC, while Wrapped accepts a client timezone offset.
