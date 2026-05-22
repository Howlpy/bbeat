<script lang="ts">
  import { onMount } from 'svelte';
  import { AlertTriangle, Disc3, Globe, Heart, Plus } from 'lucide-svelte';
  import { api, type Album } from '$lib/api';
  import NewAlbumDialog from '$lib/components/NewAlbumDialog.svelte';

  let albums = $state<Album[]>([]);
  let scope = $state<'all' | 'mine' | 'public'>('all');
  let error = $state<string | null>(null);
  let loading = $state(false);
  let creating = $state(false);
  let likedCount = $state<number | null>(null);

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

  onMount(() => {
    load();
    api.likedTracks().then((r) => (likedCount = r.total)).catch(() => {});
  });
  $effect(() => {
    if (scope) load();
  });
</script>

<div class="mx-auto max-w-5xl px-4 pt-6">
  <header class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-bold">Álbumes</h1>
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex gap-1 rounded border border-slate-800 bg-slate-900 p-1 text-xs">
        <button
          onclick={() => (scope = 'all')}
          class="rounded px-3 py-1 transition"
          class:bg-slate-800={scope === 'all'}
          class:font-semibold={scope === 'all'}
        >Todos</button>
        <button
          onclick={() => (scope = 'mine')}
          class="rounded px-3 py-1 transition"
          class:bg-slate-800={scope === 'mine'}
          class:font-semibold={scope === 'mine'}
        >Míos</button>
        <button
          onclick={() => (scope = 'public')}
          class="rounded px-3 py-1 transition"
          class:bg-slate-800={scope === 'public'}
          class:font-semibold={scope === 'public'}
        >Compartidos</button>
      </div>
      <button
        onclick={() => (creating = true)}
        class="inline-flex items-center gap-1.5 rounded bg-cyan-400 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
      >
        <Plus size={14} /> Nuevo álbum
      </button>
    </div>
  </header>

  {#if error}
    <p class="inline-flex items-center gap-2 text-red-400"><AlertTriangle size={16} /> {error}</p>
  {:else if loading && albums.length === 0}
    <p class="text-sm text-slate-500">Cargando…</p>
  {:else}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      <!-- Favoritos: card fija siempre la primera -->
      <a href="/liked" class="group relative block">
        <div
          class="grid aspect-square w-full place-items-center rounded bg-gradient-to-br from-cyan-400 to-sky-700 text-slate-950 transition group-hover:opacity-90"
        >
          <Heart size={48} fill="currentColor" />
        </div>
        <div class="mt-2 truncate text-sm font-medium">Favoritos</div>
        <div class="truncate text-xs text-slate-500">
          {likedCount === null ? '…' : `${likedCount} ${likedCount === 1 ? 'canción' : 'canciones'}`}
        </div>
      </a>
      {#each albums as album (album.id)}
        <a href="/albums/{album.id}" class="group relative block">
          {#if album.cover_url}
            <img
              src={album.cover_url}
              alt={album.title}
              class="aspect-square w-full rounded object-cover transition group-hover:opacity-80"
            />
          {:else}
            <div class="grid aspect-square w-full place-items-center rounded bg-slate-800 text-slate-700">
              <Disc3 size={44} />
            </div>
          {/if}
          <div class="absolute right-1 top-1 flex flex-col items-end gap-1">
            {#if album.is_mine}
              <span class="rounded bg-cyan-400/90 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-slate-950">
                mío
              </span>
            {/if}
            {#if album.is_public}
              <span
                class="inline-flex items-center gap-0.5 rounded bg-sky-500/80 px-1.5 py-0.5 text-[9px] font-semibold text-slate-950"
                title="Compartido"
              ><Globe size={9} /></span>
            {/if}
          </div>
          <div class="mt-2 truncate text-sm font-medium">{album.title}</div>
          <div class="truncate text-xs text-slate-500">
            {album.artist_name}{#if album.year} · {album.year}{/if}
          </div>
        </a>
      {/each}
    </div>
    {#if albums.length === 0}
      <p class="mt-4 text-center text-sm text-slate-500">
        {#if scope === 'mine'}
          No tienes álbumes propios. Crea uno o importa desde
          <a href="/import" class="text-cyan-400 underline">/import</a>.
        {:else if scope === 'public'}
          No hay álbumes compartidos.
        {:else}
          Aún no hay álbumes.
        {/if}
      </p>
    {/if}
  {/if}
</div>

{#if creating}
  <NewAlbumDialog onclose={() => (creating = false)} oncreated={load} />
{/if}
