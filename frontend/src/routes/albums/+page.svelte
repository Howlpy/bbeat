<script lang="ts">
  import { onMount } from 'svelte';
  import {
    AlertTriangle,
    Bookmark,
    BookmarkCheck,
    Disc3,
    Heart,
    ListMusic,
    Plus,
    Search
  } from 'lucide-svelte';
  import { api, type Album } from '$lib/api';
  import NewAlbumDialog from '$lib/components/NewAlbumDialog.svelte';

  let albums = $state<Album[]>([]);
  let view = $state<'saved' | 'explore'>('saved');
  let q = $state('');
  let error = $state<string | null>(null);
  let loading = $state(false);
  let creating = $state(false);
  let likedCount = $state<number | null>(null);
  let savingIds = $state<Set<number>>(new Set());

  let debounce: ReturnType<typeof setTimeout> | undefined;

  async function load() {
    loading = true;
    try {
      const res = await api.albums(view === 'saved' ? 'saved' : 'all', { q: q.trim() || undefined });
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

  // Recarga al cambiar de pestaña (inmediato) o de búsqueda (con debounce).
  let firstRun = true;
  $effect(() => {
    view; q;
    if (firstRun) { firstRun = false; return; }
    clearTimeout(debounce);
    debounce = setTimeout(load, 250);
  });

  async function toggleSave(e: MouseEvent, album: Album) {
    e.preventDefault();
    e.stopPropagation();
    if (savingIds.has(album.id)) return;
    savingIds = new Set(savingIds).add(album.id);
    const next = !album.is_saved;
    album.is_saved = next; // optimista
    try {
      if (next) await api.saveAlbum(album.id);
      else await api.unsaveAlbum(album.id);
      // En la pestaña Guardados, quitar de la lista al dejar de guardarlo.
      if (!next && view === 'saved') albums = albums.filter((a) => a.id !== album.id);
    } catch (err) {
      album.is_saved = !next; // revertir
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      const s = new Set(savingIds);
      s.delete(album.id);
      savingIds = s;
    }
  }
</script>

<div class="mx-auto max-w-5xl px-4 pt-6">
  <header class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <h1 class="text-2xl font-bold">Álbumes</h1>
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex gap-1 rounded border border-slate-800 bg-slate-900 p-1 text-xs">
        <button
          onclick={() => (view = 'saved')}
          class="rounded px-3 py-1 transition"
          class:bg-slate-800={view === 'saved'}
          class:font-semibold={view === 'saved'}
        >Guardados</button>
        <button
          onclick={() => (view = 'explore')}
          class="rounded px-3 py-1 transition"
          class:bg-slate-800={view === 'explore'}
          class:font-semibold={view === 'explore'}
        >Explorar</button>
      </div>
      <button
        onclick={() => (creating = true)}
        class="inline-flex items-center gap-1.5 rounded bg-cyan-400 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
      >
        <Plus size={14} /> Nueva playlist
      </button>
    </div>
  </header>

  <label class="mb-4 flex items-center gap-2 rounded border border-slate-800 bg-slate-900 px-3 py-2">
    <Search size={16} class="text-slate-500" />
    <input
      bind:value={q}
      placeholder={view === 'saved' ? 'Buscar en tus guardados…' : 'Buscar en todo el catálogo…'}
      class="w-full bg-transparent text-sm focus:outline-none"
    />
  </label>

  {#if error}
    <p class="inline-flex items-center gap-2 text-red-400"><AlertTriangle size={16} /> {error}</p>
  {:else if loading && albums.length === 0}
    <p class="text-sm text-slate-500">Cargando…</p>
  {:else}
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      <!-- Favoritos: card fija siempre la primera en Guardados, sin búsqueda. -->
      {#if view === 'saved' && !q.trim()}
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
      {/if}
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
              {#if album.kind === 'playlist'}<ListMusic size={44} />{:else}<Disc3 size={44} />{/if}
            </div>
          {/if}
          <!-- Botón guardar/quitar -->
          <button
            onclick={(e) => toggleSave(e, album)}
            class="absolute right-1 top-1 grid size-8 place-items-center rounded-full bg-slate-950/70 backdrop-blur transition hover:bg-slate-900"
            class:text-cyan-400={album.is_saved}
            class:text-slate-300={!album.is_saved}
            title={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
            aria-label={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
          >
            {#if album.is_saved}<BookmarkCheck size={16} />{:else}<Bookmark size={16} />{/if}
          </button>
          {#if album.kind === 'playlist'}
            <span class="absolute left-1 top-1 inline-flex items-center gap-1 rounded bg-slate-950/70 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-cyan-300 backdrop-blur">
              <ListMusic size={9} /> playlist
            </span>
          {/if}
          <div class="mt-2 truncate text-sm font-medium">{album.title}</div>
          <div class="truncate text-xs text-slate-500">
            {album.artist_name}{#if album.year} · {album.year}{/if}
          </div>
        </a>
      {/each}
    </div>
    {#if albums.length === 0}
      <p class="mt-4 text-center text-sm text-slate-500">
        {#if q.trim()}
          Nada coincide con “{q.trim()}”.
        {:else if view === 'saved'}
          No tienes nada guardado. Ve a <button class="text-cyan-400 underline" onclick={() => (view = 'explore')}>Explorar</button> para guardar álbumes, o crea una playlist.
        {:else}
          Aún no hay álbumes en el servidor. Importa desde <a href="/import" class="text-cyan-400 underline">/import</a>.
        {/if}
      </p>
    {/if}
  {/if}
</div>

{#if creating}
  <NewAlbumDialog onclose={() => (creating = false)} oncreated={load} />
{/if}
