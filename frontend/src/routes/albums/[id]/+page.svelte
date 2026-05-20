<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, type Track, type Album } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';
  import { player } from '$lib/player.svelte';

  const albumId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let album = $state<Album | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const [trackRes, albumsRes] = await Promise.all([
        api.tracks({ album_id: albumId, limit: 500 }),
        api.albums()
      ]);
      tracks = trackRes.items;
      album = albumsRes.items.find((a) => a.id === albumId) ?? null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });

  function playAll() {
    if (tracks.length) player.playTracks(tracks, 0);
  }
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if album}
    <div class="mb-6 flex flex-col items-start gap-4 sm:flex-row sm:items-end">
      {#if album.cover_url}
        <img src={album.cover_url} alt="" class="size-40 flex-none rounded-md object-cover" />
      {:else}
        <div class="grid size-40 flex-none place-items-center rounded-md bg-neutral-800 text-5xl text-neutral-600">◉</div>
      {/if}
      <div class="min-w-0 flex-1">
        <h1 class="text-2xl font-bold">{album.title}</h1>
        <div class="text-sm text-neutral-400">
          {album.artist_name}{#if album.year} · {album.year}{/if} · {album.track_count} pistas
        </div>
        <button
          onclick={playAll}
          class="mt-3 rounded-md bg-emerald-500 px-4 py-1.5 text-sm font-medium text-neutral-950 hover:bg-emerald-400"
        >▶ Reproducir álbum</button>
      </div>
    </div>

    <TrackList {tracks} showAlbum={false} />
  {:else}
    <p class="text-neutral-500">Cargando…</p>
  {/if}
</div>
