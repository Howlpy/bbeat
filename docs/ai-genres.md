# AI genre classifier

An optional feature, **disabled by default**, that uses an LLM to review the genre of each **artist**. It has no dependency on any single provider.

For how genres are detected without AI, see [genres.md](./genres.md).

## How it works

- The model receives the artist's tracks, their current genres and, if configured, snippets from a web search. It picks one genre from Bbeat's closed list, or `unknown` if it is not sure, and only flags per-track exceptions when the evidence is clear.
- A suggestion is applied only if its confidence is at least `BBEAT_AI_MIN_CONFIDENCE` (default `0.75`). Everything else goes to **Admin, AI genres, Review suggestions**, where you can accept, reject or change the genre.
- A track whose genre you edit by hand (or a whole artist, edited from the artist page, admin only) is **locked**: neither the AI nor `backfill_genres` touches it again.
- Runs are resumable. If the provider runs out of quota (HTTP 429) the run stops cleanly; run it again later and it continues with the pending artists.
- Separately, and without needing AI, when an imported track's genre disagrees with its artist's (at least 3 tracks and at least 80% agreement) the artist's genre is kept (`BBEAT_ARTIST_CONSISTENCY`). With AI enabled, unknown or disputed cases are queued in the background.

## Configuration

All variables are optional and go in `backend/.env`.

| Variable | Default | Notes |
|---|---|---|
| `BBEAT_AI_PROVIDER` | `none` | `openai`, `gemini`, `anthropic`, `ollama` or `none` |
| `BBEAT_AI_API_KEY` | empty | Not needed for local Ollama / LM Studio |
| `BBEAT_AI_MODEL` | per provider | `gemini-2.5-flash-lite` (gemini), `gpt-4o-mini` (openai), `claude-haiku-4-5` (anthropic), `llama3.2` (ollama) |
| `BBEAT_AI_BASE_URL` | per provider | Gemini (OpenAI-compatible endpoint), `https://api.openai.com/v1`, `https://api.anthropic.com`, `http://localhost:11434/v1`. Override for any OpenAI-compatible server |
| `BBEAT_AI_RPM` | `10` | Requests per minute; adjust to your quota |
| `BBEAT_AI_TIMEOUT` | `60` | Seconds per request |
| `BBEAT_AI_MIN_CONFIDENCE` | `0.75` | Threshold to apply without review |
| `BBEAT_AI_BATCH_ARTISTS` | `5` | Small artists (10 tracks or fewer) sharing one request |
| `BBEAT_SEARCH_PROVIDER` | `none` | `searxng` or `none`. Web evidence helps a lot with lesser-known artists |
| `BBEAT_SEARXNG_URL` | empty | For example `http://localhost:8080`; SearXNG needs its JSON format enabled |
| `BBEAT_ARTIST_CONSISTENCY` | `true` | Per-artist consistency on import |

## Provider examples

```ini
# Google Gemini (free key at https://aistudio.google.com/apikey; low daily quota)
BBEAT_AI_PROVIDER=gemini
BBEAT_AI_API_KEY=AIza...

# OpenRouter (any OpenAI-compatible API works the same way)
BBEAT_AI_PROVIDER=openai
BBEAT_AI_BASE_URL=https://openrouter.ai/api/v1
BBEAT_AI_API_KEY=sk-or-...
BBEAT_AI_MODEL=meta-llama/llama-3.3-70b-instruct

# Groq
BBEAT_AI_PROVIDER=openai
BBEAT_AI_BASE_URL=https://api.groq.com/openai/v1
BBEAT_AI_API_KEY=gsk_...
BBEAT_AI_MODEL=<a model available on Groq>

# Ollama (local, no key)
BBEAT_AI_PROVIDER=ollama
BBEAT_AI_MODEL=llama3.1:8b

# OpenAI
BBEAT_AI_PROVIDER=openai
BBEAT_AI_API_KEY=sk-...

# Anthropic
BBEAT_AI_PROVIDER=anthropic
BBEAT_AI_API_KEY=sk-ant-...

# Optional web evidence via your own SearXNG (combine with any of the above)
BBEAT_SEARCH_PROVIDER=searxng
BBEAT_SEARXNG_URL=http://localhost:8080
```

## Command line

Run from `backend/`. With Docker: `docker compose exec bbeat python -m scripts.ai_genres ...`.

```bash
python -m scripts.ai_genres --limit 20 --report report.csv   # dry run: writes nothing
python -m scripts.ai_genres --apply --limit 100              # apply, queue doubtful ones
python -m scripts.ai_genres --apply --only-missing           # only artists with untagged tracks
python -m scripts.ai_genres --artist "Artist Name" --force --apply   # reclassify one artist
```

Options: `--apply` (without it, it is a dry run), `--limit N`, `--artist NAME` (repeatable), `--force`, `--only-missing`, `--suspicious` (artists with no genre, mixed genres, or only 1-2 tracks), `--report FILE.csv`.

The dry run does not save progress (it spends quota every time); `--apply` is resumable.
