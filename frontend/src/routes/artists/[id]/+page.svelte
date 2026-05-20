<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, type Track, type Artist } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';

  const artistId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let artist = $state<Artist | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const [trackRes, artistsRes] = await Promise.all([
        api.tracks({ artist_id: artistId, limit: 500 }),
        api.artists()
      ]);
      tracks = trackRes.items;
      artist = artistsRes.items.find((a) => a.id === artistId) ?? null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if artist}
    <header class="mb-4">
      <h1 class="text-2xl font-bold">{artist.name}</h1>
      <p class="text-xs text-neutral-500">{artist.album_count} álbumes · {artist.track_count} pistas</p>
    </header>
    <TrackList {tracks} />
  {:else}
    <p class="text-neutral-500">Cargando…</p>
  {/if}
</div>
