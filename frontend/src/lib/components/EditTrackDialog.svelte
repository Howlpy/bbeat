<script lang="ts">
  import { AlertTriangle, X } from 'lucide-svelte';
  import { api, type Album, type Track } from '$lib/api';
  import { GENRE_SLUGS, genreLabel } from '$lib/genres';

  let {
    track,
    albums = [],
    onclose,
    onsaved
  }: {
    track: Track;
    albums?: Album[];
    onclose: () => void;
    onsaved?: () => void;
  } = $props();

  let title = $state(track.title);
  let artist = $state(track.artist_name);
  let album = $state(track.album_title ?? "");
  // svelte-ignore state_referenced_locally
  let genre = $state(track.genre ?? "");
  let year = $state(track.album_year ? String(track.album_year) : '');
  let trackNumber = $state(track.track_number ? String(track.track_number) : '');
  let mode = $state<'edit' | 'move'>('edit');
  let targetAlbumId = $state<number | null>(null);
  let saving = $state(false);
  let error = $state<string | null>(null);

  async function save() {
    saving = true;
    error = null;
    try {
      if (mode === 'move' && targetAlbumId) {
        await api.editTrack(track.id, { target_album_id: targetAlbumId, title: title.trim() });
      } else {
        const body: Parameters<typeof api.editTrack>[1] = {};
        if (title.trim() && title !== track.title) body.title = title.trim();
        if (artist.trim() && artist !== track.artist_name) body.artist = artist.trim();
        if (album !== (track.album_title ?? '')) body.album = album.trim();
        if (year && Number(year) !== track.album_year) body.year = Number(year);
        if (genre !== (track.genre ?? "")) body.genre = genre.trim();
        const tn = Number(trackNumber);
        if (trackNumber && tn !== track.track_number) body.track_number = tn;
        if (Object.keys(body).length === 0) {
          onclose();
          return;
        }
        await api.editTrack(track.id, body);
      }
      onsaved?.();
      onclose();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center" onclick={onclose}>
  <div
    class="w-full max-w-md rounded-t-xl border border-line bg-surface p-5 shadow-xl sm:rounded-xl"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="mb-4 flex items-baseline justify-between">
      <h2 class="text-lg font-semibold">Editar pista</h2>
      <button onclick={onclose} class="grid size-10 place-items-center rounded-lg text-fg-subtle hover:bg-surface-2" aria-label="Cerrar"><X size={16} /></button>
    </header>

    <div class="mb-3 flex gap-2 text-xs">
      <button
        onclick={() => (mode = 'edit')}
        class="flex-1 rounded-lg border px-3 py-1.5"
        class:border-accent={mode === 'edit'}
        class:bg-accent={mode === 'edit'}
        class:text-accent-fg={mode === 'edit'}
        class:border-line={mode !== 'edit'}
      >Editar metadata</button>
      <button
        onclick={() => (mode = 'move')}
        class="flex-1 rounded-lg border px-3 py-1.5"
        class:border-accent={mode === 'move'}
        class:bg-accent={mode === 'move'}
        class:text-accent-fg={mode === 'move'}
        class:border-line={mode !== 'move'}
        disabled={albums.length === 0}
      >Mover de álbum</button>
    </div>

    {#if track.source_url}
      <div class="mb-3 rounded-lg border border-line bg-bg px-3 py-2 text-xs min-h-11 sm:min-h-10">
        <div class="text-fg-subtle">Fuente</div>
        <a
          href={track.source_url}
          target="_blank"
          rel="noopener noreferrer"
          class="block truncate text-accent hover:underline"
          title={track.source_url}
        >{track.source_url}</a>
        <p class="mt-1 text-xs text-fg-subtle">
          ¿No es la pista correcta? Bórrala y vuelve a importarla.
        </p>
      </div>
    {/if}

    {#if mode === 'edit'}
      <div class="space-y-2 text-sm">
        <label class="block">
          <span class="text-xs text-fg-muted">Título</span>
          <input
            bind:value={title}
            class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
          />
        </label>
        <label class="block">
          <span class="text-xs text-fg-muted">Artista</span>
          <input
            bind:value={artist}
            class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
          />
        </label>
        <label class="block">
          <span class="text-xs text-fg-muted">Álbum</span>
          <input
            bind:value={album}
            class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
          />
        </label>
        <label class="block">
          <span class="text-xs text-fg-muted">Género</span>
          <!-- El datalist sugiere el vocabulario canónico (en minúsculas, que
               es como se guarda), pero sigue siendo texto libre a propósito. -->
          <input
            bind:value={genre}
            placeholder="Sin género"
            list="bbeat-genres"
            class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
          />
          <datalist id="bbeat-genres">
            {#each GENRE_SLUGS as slug (slug)}
              <option value={slug}>{genreLabel(slug)}</option>
            {/each}
          </datalist>
        </label>
        <div class="flex gap-2">
          <label class="block flex-1">
            <span class="text-xs text-fg-muted">Año</span>
            <input
              type="number"
              bind:value={year}
              min="1900"
              max="2100"
              class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
            />
          </label>
          <label class="block flex-1">
            <span class="text-xs text-fg-muted">Nº pista</span>
            <input
              type="number"
              bind:value={trackNumber}
              min="1"
              class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
            />
          </label>
        </div>
      </div>
    {:else}
      <label class="block text-sm">
        <span class="text-xs text-fg-muted">Mover a álbum existente</span>
        <select
          bind:value={targetAlbumId}
          class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
        >
          <option value={null}>— selecciona —</option>
          {#each albums as a}
            <option value={a.id}>{a.title} · {a.artist_name} ({a.track_count})</option>
          {/each}
        </select>
      </label>
    {/if}

    {#if error}
      <p class="mt-3 inline-flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 p-2 text-xs text-danger"><AlertTriangle size={14} /> {error}</p>
    {/if}

    <div class="mt-5 flex gap-2">
      <button onclick={onclose} class="flex-1 rounded-lg border border-line px-4 py-2 text-sm hover:bg-surface-2 min-h-11 sm:min-h-10">
        Cancelar
      </button>
      <button
        onclick={save}
        disabled={saving || (mode === 'move' && !targetAlbumId)}
        class="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:bg-accent-hover disabled:opacity-50 min-h-11 sm:min-h-10"
      >
        {saving ? 'Guardando…' : 'Guardar'}
      </button>
    </div>
  </div>
</div>
