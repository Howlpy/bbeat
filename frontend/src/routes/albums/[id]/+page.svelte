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
  let coverInput = $state<HTMLInputElement | null>(null);
  let uploading = $state(false);
  let coverMsg = $state<string | null>(null);
  let coverNonce = $state(0);

  async function load() {
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
  }

  onMount(load);

  function playAll() {
    if (tracks.length) player.playTracks(tracks, 0);
  }

  async function onCoverUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !album) return;
    uploading = true;
    coverMsg = null;
    try {
      const r = await api.uploadAlbumCover(album.id, file);
      coverMsg = `Carátula actualizada en ${r.tracks_updated} ${r.tracks_updated === 1 ? 'pista' : 'pistas'}.`;
      coverNonce++; // force <img> refresh
      await load();
    } catch (err) {
      coverMsg = err instanceof Error ? err.message : String(err);
    } finally {
      uploading = false;
      if (coverInput) coverInput.value = '';
    }
  }
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if album}
    <div class="mb-6 flex flex-col items-start gap-4 sm:flex-row sm:items-end">
      <div class="relative flex-none">
        {#if album.cover_url}
          <img
            src="{album.cover_url}?v={coverNonce}"
            alt=""
            class="size-40 rounded-md object-cover"
          />
        {:else}
          <div class="grid size-40 place-items-center rounded-md bg-neutral-800 text-5xl text-neutral-600">◉</div>
        {/if}
        <label
          class="absolute bottom-1 right-1 cursor-pointer rounded-full bg-neutral-900/90 px-2 py-1 text-xs text-neutral-200 backdrop-blur hover:bg-neutral-800"
          title="Cambiar carátula"
        >
          <input
            bind:this={coverInput}
            type="file"
            accept="image/jpeg,image/png"
            class="hidden"
            onchange={onCoverUpload}
            disabled={uploading}
          />
          {uploading ? '…' : '📷'}
        </label>
      </div>
      <div class="min-w-0 flex-1">
        <h1 class="text-2xl font-bold">{album.title}</h1>
        <div class="text-sm text-neutral-400">
          {album.artist_name}{#if album.year} · {album.year}{/if} · {album.track_count} pistas
        </div>
        <button
          onclick={playAll}
          class="mt-3 rounded-md bg-emerald-500 px-4 py-1.5 text-sm font-medium text-neutral-950 hover:bg-emerald-400"
        >▶ Reproducir álbum</button>
        {#if coverMsg}
          <p class="mt-2 text-xs text-emerald-400">{coverMsg}</p>
        {/if}
      </div>
    </div>

    <TrackList {tracks} showAlbum={false} />
  {:else}
    <p class="text-neutral-500">Cargando…</p>
  {/if}
</div>
