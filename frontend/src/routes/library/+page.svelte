<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Track } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';

  let tracks = $state<Track[]>([]);
  let total = $state(0);
  let error = $state<string | null>(null);
  let query = $state('');
  let searching = $state(false);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;

  async function load() {
    try {
      const res = await api.tracks({ limit: 500 });
      tracks = res.items;
      total = res.total;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function doSearch(q: string) {
    if (!q.trim()) {
      await load();
      return;
    }
    searching = true;
    try {
      const r = await api.search(q.trim());
      tracks = r.items;
      total = r.total;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      searching = false;
    }
  }

  function onQueryChange() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => doSearch(query), 250);
  }

  onMount(load);
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
    <h1 class="text-2xl font-bold">Canciones</h1>
    <span class="text-xs text-slate-500">{total} {query ? 'resultados' : 'en biblioteca'}</span>
  </header>

  <div class="relative mb-4">
    <input
      type="search"
      bind:value={query}
      oninput={onQueryChange}
      placeholder="Buscar título, artista, álbum…"
      class="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 pr-9 text-sm placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
    />
    {#if searching}
      <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-sky-400">…</span>
    {:else if query}
      <button
        onclick={() => { query = ''; load(); }}
        class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:bg-slate-800"
        aria-label="Limpiar"
      >✕</button>
    {/if}
  </div>

  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if tracks.length === 0}
    <p class="rounded-md border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
      {query ? 'Sin resultados.' : 'Biblioteca vacía. Importa algo desde /import.'}
    </p>
  {:else}
    <TrackList bind:tracks onchanged={load} />
  {/if}
</div>
