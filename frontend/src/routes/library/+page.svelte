<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Track } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';

  let tracks = $state<Track[]>([]);
  let total = $state(0);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const res = await api.tracks({ limit: 500 });
      tracks = res.items;
      total = res.total;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex items-baseline justify-between">
    <h1 class="text-2xl font-bold">Canciones</h1>
    <span class="text-xs text-neutral-500">{total} en biblioteca</span>
  </header>

  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if tracks.length === 0}
    <p class="rounded-md border border-neutral-800 bg-neutral-900 p-4 text-sm text-neutral-400">
      Vacío. Mete archivos en <code class="bg-neutral-800 px-1">data/music/</code> y re-escanea desde el home.
    </p>
  {:else}
    <TrackList {tracks} />
  {/if}
</div>
