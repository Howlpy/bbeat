<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Artist } from '$lib/api';

  let artists = $state<Artist[]>([]);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const res = await api.artists();
      artists = res.items;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <h1 class="mb-4 text-2xl font-bold">Artistas</h1>

  {#if error}
    <p class="text-red-400">{error}</p>
  {:else if artists.length === 0}
    <p class="text-sm text-slate-500">Sin artistas todavía.</p>
  {:else}
    <ul class="divide-y divide-slate-900">
      {#each artists as artist}
        <li>
          <a href="/artists/{artist.id}" class="flex items-center justify-between px-2 py-3 hover:bg-slate-900">
            <div class="font-medium">{artist.name}</div>
            <div class="text-xs text-slate-500">
              {artist.album_count} álb · {artist.track_count} pistas
            </div>
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</div>
