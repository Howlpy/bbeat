<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Album } from '$lib/api';

  let albums = $state<Album[]>([]);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const res = await api.albums();
      albums = res.items;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

<div class="mx-auto max-w-5xl px-4 pt-6">
  <h1 class="mb-4 text-2xl font-bold">Álbumes</h1>

  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if albums.length === 0}
    <p class="text-sm text-neutral-500">Sin álbumes todavía.</p>
  {:else}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {#each albums as album}
        <a href="/albums/{album.id}" class="group">
          {#if album.cover_url}
            <img
              src={album.cover_url}
              alt={album.title}
              class="aspect-square w-full rounded-md object-cover transition group-hover:opacity-80"
            />
          {:else}
            <div class="grid aspect-square w-full place-items-center rounded-md bg-neutral-800 text-3xl text-neutral-600">
              ◉
            </div>
          {/if}
          <div class="mt-2 truncate text-sm font-medium">{album.title}</div>
          <div class="truncate text-xs text-neutral-500">
            {album.artist_name}{#if album.year} · {album.year}{/if}
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>
