<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { api, type Track, type Artist } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, type TrackSort } from '$lib/sort';
  import { player } from '$lib/player.svelte';
  import { Play, Shuffle } from 'lucide-svelte';
  import { avatarGradient, initials, hueFor } from '$lib/visual';

  const artistId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let sort = $state<TrackSort>('original');
  const visibleTracks = $derived(sortTracks(tracks, sort));
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
    <p class="text-red-400">{error}</p>
  {:else if artist}
    <div
      class="pointer-events-none fixed inset-x-0 top-0 -z-10 h-72"
      style:background="radial-gradient(ellipse 90% 60% at 50% 0%, hsl({hueFor(artist.name)} 55% 38% / 0.5), transparent 70%)"
    ></div>
    <header class="mb-5 flex items-center gap-4">
      <span
        class="grid size-20 flex-none place-items-center rounded-2xl text-2xl font-bold text-white/90 shadow-lg"
        style:background={avatarGradient(artist.name)}
      >{initials(artist.name)}</span>
      <div class="min-w-0">
        <h1 class="truncate text-2xl font-bold">{artist.name}</h1>
        <p class="text-xs text-slate-500">{artist.album_count} álbumes · {artist.track_count} pistas</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            onclick={() => tracks.length && player.playTracks(tracks, 0)}
            class="inline-flex items-center gap-1.5 rounded-full bg-cyan-500 px-4 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
          ><Play size={15} fill="currentColor" /> Reproducir</button>
          <button
            onclick={() => tracks.length && player.playShuffled(tracks)}
            class="inline-flex items-center gap-1.5 rounded-full border border-slate-700 px-4 py-1.5 text-sm transition hover:bg-slate-800"
          ><Shuffle size={15} /> Aleatorio</button>
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
    <p class="text-slate-500">Cargando…</p>
  {/if}
</div>
