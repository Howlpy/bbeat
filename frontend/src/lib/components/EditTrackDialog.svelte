<script lang="ts">
  import { api, type Album, type Track } from '$lib/api';

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
  let album = $state(track.album_title ?? '');
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

<div class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center" onclick={onclose}>
  <div
    class="w-full max-w-md rounded-t-xl border border-slate-800 bg-slate-900 p-5 shadow-xl sm:rounded-xl"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="mb-4 flex items-baseline justify-between">
      <h2 class="text-lg font-semibold">Editar pista</h2>
      <button onclick={onclose} class="rounded p-1 text-slate-500 hover:bg-slate-800">✕</button>
    </header>

    <div class="mb-3 flex gap-2 text-xs">
      <button
        onclick={() => (mode = 'edit')}
        class="flex-1 rounded border px-3 py-1.5"
        class:border-cyan-500={mode === 'edit'}
        class:bg-cyan-500={mode === 'edit'}
        class:text-slate-950={mode === 'edit'}
        class:border-slate-800={mode !== 'edit'}
      >Editar metadata</button>
      <button
        onclick={() => (mode = 'move')}
        class="flex-1 rounded border px-3 py-1.5"
        class:border-cyan-500={mode === 'move'}
        class:bg-cyan-500={mode === 'move'}
        class:text-slate-950={mode === 'move'}
        class:border-slate-800={mode !== 'move'}
        disabled={albums.length === 0}
      >Mover de álbum</button>
    </div>

    {#if track.source_url}
      <div class="mb-3 rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs">
        <div class="text-slate-500">Fuente</div>
        <a
          href={track.source_url}
          target="_blank"
          rel="noopener noreferrer"
          class="block truncate text-cyan-400 hover:underline"
          title={track.source_url}
        >{track.source_url}</a>
        <p class="mt-1 text-[10px] text-slate-600">
          ¿No es la pista correcta? Bórrala y vuelve a importarla.
        </p>
      </div>
    {/if}

    {#if mode === 'edit'}
      <div class="space-y-2 text-sm">
        <label class="block">
          <span class="text-xs text-slate-400">Título</span>
          <input
            bind:value={title}
            class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
          />
        </label>
        <label class="block">
          <span class="text-xs text-slate-400">Artista</span>
          <input
            bind:value={artist}
            class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
          />
        </label>
        <label class="block">
          <span class="text-xs text-slate-400">Álbum</span>
          <input
            bind:value={album}
            class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
          />
        </label>
        <div class="flex gap-2">
          <label class="block flex-1">
            <span class="text-xs text-slate-400">Año</span>
            <input
              type="number"
              bind:value={year}
              min="1900"
              max="2100"
              class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
            />
          </label>
          <label class="block flex-1">
            <span class="text-xs text-slate-400">Nº pista</span>
            <input
              type="number"
              bind:value={trackNumber}
              min="1"
              class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
            />
          </label>
        </div>
      </div>
    {:else}
      <label class="block text-sm">
        <span class="text-xs text-slate-400">Mover a álbum existente</span>
        <select
          bind:value={targetAlbumId}
          class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
        >
          <option value={null}>— selecciona —</option>
          {#each albums as a}
            <option value={a.id}>{a.title} · {a.artist_name} ({a.track_count})</option>
          {/each}
        </select>
      </label>
    {/if}

    {#if error}
      <p class="mt-3 rounded border border-red-900/50 bg-red-950/30 p-2 text-xs text-red-300">⚠️ {error}</p>
    {/if}

    <div class="mt-5 flex gap-2">
      <button onclick={onclose} class="flex-1 rounded border border-slate-800 px-4 py-2 text-sm hover:bg-slate-800">
        Cancelar
      </button>
      <button
        onclick={save}
        disabled={saving || (mode === 'move' && !targetAlbumId)}
        class="flex-1 rounded bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
      >
        {saving ? 'Guardando…' : 'Guardar'}
      </button>
    </div>
  </div>
</div>
