<script lang="ts">
  import { onMount } from 'svelte';
  import { X, Shuffle, Heart } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, type TrackSort } from '$lib/sort';

  let tracks = $state<Track[]>([]);
  let total = $state(0);
  let error = $state<string | null>(null);
  let query = $state('');
  let searching = $state(false);
  let loading = $state(true);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  let sort = $state<TrackSort>('original');
  const visibleTracks = $derived(sortTracks(tracks, sort));

  async function load() {
    try {
      const res = await api.tracks({ limit: 500 });
      tracks = res.items;
      total = res.total;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
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

  function shuffleAll() {
    if (tracks.length) player.playShuffled(tracks);
  }

  onMount(load);
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
    <h1 class="text-2xl font-bold">Canciones</h1>
    <div class="flex items-center gap-3">
      <a
        href="/liked"
        class="inline-flex items-center gap-1.5 text-xs text-slate-400 transition hover:text-cyan-400"
      ><Heart size={14} /> Favoritos</a>
      <span class="text-xs text-slate-500">{total} {query ? 'resultados' : 'en biblioteca'}</span>
    </div>
  </header>

  {#if tracks.length > 0}
    <button
      onclick={shuffleAll}
      class="mb-4 inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
    >
      <Shuffle size={16} /> Reproducir aleatorio
    </button>
  {/if}

  <div class="mb-4 flex items-center gap-2">
    <div class="relative min-w-0 flex-1">
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
      ><X size={14} /></button>
    {/if}
    </div>
    <SortSelect prefKey="sort:library" bind:value={sort} originalLabel="Orden de la biblioteca" />
  </div>

  {#if error}
    <p class="text-red-400">{error}</p>
  {:else if loading && tracks.length === 0}
    <ul class="divide-y divide-slate-900">
      {#each Array(8) as _, i (i)}
        <li class="flex items-center gap-3 px-2 py-2">
          <div class="size-10 flex-none animate-pulse rounded bg-slate-800"></div>
          <div class="flex-1 space-y-2">
            <div class="h-3 w-1/2 animate-pulse rounded bg-slate-800"></div>
            <div class="h-2.5 w-1/3 animate-pulse rounded bg-slate-800"></div>
          </div>
        </li>
      {/each}
    </ul>
  {:else if tracks.length === 0}
    <p class="rounded-md border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
      {query ? 'Sin resultados.' : 'Biblioteca vacía. Importa algo desde /import.'}
    </p>
  {:else}
    <TrackList tracks={visibleTracks} showAlbum={sort === 'album'} showGenre={sort === 'genre'} onchanged={load} />
  {/if}
</div>
