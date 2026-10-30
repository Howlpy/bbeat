<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import { Heart, Shuffle, Play } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import DownloadAllButton from '$lib/components/DownloadAllButton.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
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
      error = null;
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

  onMount(() => onReconnect(load));
  onMount(load);
</script>

<div class="page-narrow">
  <BackButton fallback="/library" />
  <header class="mb-6 flex items-center gap-4">
    <span
      class="grid size-14 flex-none place-items-center rounded-xl bg-accent-soft text-accent"
    >
      <Heart size={26} fill="currentColor" />
    </span>
    <div>
      <h1 class="page-title">Favoritos</h1>
      <p class="text-sm text-fg-muted">{total} {total === 1 ? 'canción' : 'canciones'}</p>
    </div>
  </header>

  {#if tracks.length > 0}
    <!-- flex-wrap: con cuatro controles esta fila no cabe en un móvil; sin
         envolver desbordaba la página entera y rompía el layout en la APK. -->
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <Button variant="primary" onclick={playAll}><Play size={16} fill="currentColor" /> Reproducir</Button>
      <Button onclick={shuffleAll}><Shuffle size={16} /> Aleatorio</Button>
      <DownloadAllButton {tracks} label="Guardar offline" />
      <div class="ml-auto"><SortSelect prefKey="sort:liked" bind:value={sort} originalLabel="Más recientes" /></div>
    </div>
  {/if}

  {#if error}
    <ErrorState {error} />
  {:else if loading}
    <div class="space-y-2">
      {#each Array(6) as _}<Skeleton class="h-14 w-full" />{/each}
    </div>
  {:else if tracks.length === 0}
    <EmptyState icon={Heart} title="Aún no tienes favoritos" text="Dale al corazón en cualquier canción para guardarla aquí." />
  {:else}
    <TrackList tracks={visibleTracks} showGenre={sort === 'genre'} onchanged={load} />
  {/if}
</div>
