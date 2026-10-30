<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import { page } from '$app/state';
  import { api, type Track, type Artist } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, type TrackSort } from '$lib/sort';
  import { player } from '$lib/player.svelte';
  import { Play, Shuffle } from 'lucide-svelte';
  import { initials } from '$lib/visual';
  import Button from '$lib/components/ui/Button.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';

  const artistId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let sort = $state<TrackSort>('original');
  const visibleTracks = $derived(sortTracks(tracks, sort));
  let artist = $state<Artist | null>(null);
  let error = $state<string | null>(null);

  async function load() {
    try {
      const [trackRes, artistsRes] = await Promise.all([
        api.tracks({ artist_id: artistId, limit: 500 }),
        api.artists()
      ]);
      tracks = trackRes.items;
      artist = artistsRes.items.find((a) => a.id === artistId) ?? null;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(() => {
    load();
    return onReconnect(() => {
      if (error) load();
    });
  });
</script>

<div class="page-narrow">
  <BackButton fallback="/artists" />
  {#if error}
    <ErrorState {error} />
  {:else if artist}
    <header class="mb-8 flex items-center gap-4">
      <span
        class="grid size-20 flex-none place-items-center rounded-xl bg-surface-2 text-2xl font-bold text-fg-muted"
      >{initials(artist.name)}</span>
      <div class="min-w-0">
        <h1 class="page-title truncate">{artist.name}</h1>
        <p class="text-sm text-fg-muted">{artist.album_count} álbumes · {artist.track_count} pistas</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button variant="primary" onclick={() => tracks.length && player.playTracks(tracks, 0)}><Play size={16} fill="currentColor" /> Reproducir</Button>
          <Button onclick={() => tracks.length && player.playShuffled(tracks)}><Shuffle size={16} /> Aleatorio</Button>
        </div>
      </div>
    </header>
    {#if tracks.length > 0}
      <div class="mb-2 flex justify-end px-2">
        <SortSelect prefKey="sort:artist:{artistId}" bind:value={sort} originalLabel="Por álbum" />
      </div>
    {/if}
    <TrackList tracks={visibleTracks} showGenre={sort === 'genre'} />
  {:else}
    <div class="flex items-center gap-4">
      <Skeleton class="size-20 flex-none" /><Skeleton class="h-8 w-1/2" />
    </div>
    <div class="mt-8 space-y-2">
      {#each Array(6) as _}<Skeleton class="h-14 w-full" />{/each}
    </div>
  {/if}
</div>
