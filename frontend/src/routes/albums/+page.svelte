<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Album } from '$lib/api';

  let albums = $state<Album[]>([]);
  let scope = $state<'all' | 'mine' | 'public'>('all');
  let error = $state<string | null>(null);
  let loading = $state(false);

  async function load() {
    loading = true;
    try {
      const res = await api.albums(scope);
      albums = res.items;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  onMount(load);

  // Recargar al cambiar el scope
  $effect(() => {
    if (scope) load();
  });
</script>

<div class="mx-auto max-w-5xl px-4 pt-6">
  <header class="mb-4 flex flex-wrap items-baseline justify-between gap-3">
    <h1 class="text-2xl font-bold">Álbumes</h1>
    <div class="flex gap-1 rounded-md border border-slate-800 bg-slate-900 p-1 text-xs">
      <button
        onclick={() => (scope = 'all')}
        class="rounded px-3 py-1"
        class:bg-slate-800={scope === 'all'}
        class:font-semibold={scope === 'all'}
      >Todos</button>
      <button
        onclick={() => (scope = 'mine')}
        class="rounded px-3 py-1"
        class:bg-slate-800={scope === 'mine'}
        class:font-semibold={scope === 'mine'}
      >Míos</button>
      <button
        onclick={() => (scope = 'public')}
        class="rounded px-3 py-1"
        class:bg-slate-800={scope === 'public'}
        class:font-semibold={scope === 'public'}
      >Compartidos</button>
    </div>
  </header>

  {#if error}
    <p class="text-red-400">⚠️ {error}</p>
  {:else if loading && albums.length === 0}
    <p class="text-sm text-slate-500">Cargando…</p>
  {:else if albums.length === 0}
    <p class="text-sm text-slate-500">
      {#if scope === 'mine'}
        No tienes álbumes propios todavía. Importa algo desde <a href="/import" class="text-cyan-400 underline">/import</a>.
      {:else if scope === 'public'}
        No hay álbumes compartidos.
      {:else}
        Sin álbumes.
      {/if}
    </p>
  {:else}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      {#each albums as album (album.id)}
        <a href="/albums/{album.id}" class="group relative">
          {#if album.cover_url}
            <img
              src={album.cover_url}
              alt={album.title}
              class="aspect-square w-full rounded-md object-cover transition group-hover:opacity-80"
            />
          {:else}
            <div class="grid aspect-square w-full place-items-center rounded-md bg-slate-800 text-3xl text-slate-600">◉</div>
          {/if}
          <!-- Badges -->
          <div class="absolute right-1 top-1 flex flex-col items-end gap-1">
            {#if album.is_mine}
              <span class="rounded bg-cyan-500/80 px-1.5 py-0.5 text-[9px] font-semibold text-slate-950">mío</span>
            {/if}
            {#if album.is_public}
              <span class="rounded bg-sky-500/70 px-1.5 py-0.5 text-[9px] font-semibold text-slate-950">🌍</span>
            {/if}
          </div>
          <div class="mt-2 truncate text-sm font-medium">{album.title}</div>
          <div class="truncate text-xs text-slate-500">
            {album.artist_name}{#if album.year} · {album.year}{/if}
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>
