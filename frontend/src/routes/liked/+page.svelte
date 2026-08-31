<script lang="ts">
  import { onMount } from 'svelte';
  import { Heart, Shuffle, Play } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import DownloadAllButton from '$lib/components/DownloadAllButton.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, type TrackSort } from '$lib/sort';

  let tracks = $state<Track[]>([]);
  let sort = $state<TrackSort>('original');
  const visibleTracks = $derived(sortTracks(tracks, sort));
  let total = $state(0);
  let error = $state<string | null>(null);
  let loading = $state(true);

  async function load() {
    loading = true;
    try {
      const r = await api.likedTracks();
      tracks = r.items;
      total = r.total;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function playAll() {
    if (tracks.length) player.playTracks(tracks, 0);
  }
  function shuffleAll() {
    if (tracks.length) player.playShuffled(tracks);
  }

  onMount(load);
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex items-center gap-3">
    <span
      class="grid size-14 flex-none place-items-center rounded bg-gradient-to-br from-cyan-400 to-sky-700 text-slate-950"
    >
      <Heart size={26} fill="currentColor" />
    </span>
    <div>
      <h1 class="text-2xl font-bold">Favoritos</h1>
      <p class="text-xs text-slate-500">{total} {total === 1 ? 'canción' : 'canciones'}</p>
    </div>
  </header>

  {#if tracks.length > 0}
    <!-- flex-wrap: con cuatro controles esta fila no cabe en un móvil; sin
         envolver desbordaba la página entera y rompía el layout en la APK. -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <button
        onclick={playAll}
        class="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
      >
        <Play size={16} fill="currentColor" /> Reproducir
      </button>
      <button
        onclick={shuffleAll}
        class="inline-flex items-center gap-2 rounded-full border border-slate-700 px-4 py-2 text-sm transition hover:bg-slate-800"
      >
        <Shuffle size={16} /> Aleatorio
      </button>
      <DownloadAllButton {tracks} label="Descargar todo" />
      <div class="ml-auto"><SortSelect prefKey="sort:liked" bind:value={sort} originalLabel="Más recientes" /></div>
    </div>
  {/if}

  {#if error}
    <p class="text-red-400">{error}</p>
  {:else if loading}
    <p class="text-slate-500">Cargando…</p>
  {:else if tracks.length === 0}
    <p class="rounded-md border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
      Aún no tienes favoritos. Dale al corazón en cualquier canción para guardarla aquí.
    </p>
  {:else}
    <TrackList tracks={visibleTracks} showGenre={sort === 'genre'} onchanged={load} />
  {/if}
</div>
