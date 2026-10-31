<script lang="ts">
  import { coverSrc } from '$lib/cover';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import {
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
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

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
    // Esqueleto solo si no hay nada que enseñar: recargar (reconexión, búsqueda)
    // no debe vaciar la rejilla y hacerla parpadear.
    loading = albums.length === 0;
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
    return onReconnect(load);
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

<div class="page">
  <BackButton fallback="/library" />
  <header class="mb-6 flex flex-wrap items-center justify-between gap-3">
    <h1 class="page-title">Álbumes</h1>
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex gap-1 rounded-lg bg-surface p-1 text-sm">
        <button
          onclick={() => (view = 'saved')}
          class="min-h-10 rounded-md px-4 text-fg-muted transition sm:min-h-9"
          class:bg-surface-3={view === 'saved'}
          class:text-fg={view === 'saved'}
          class:font-semibold={view === 'saved'}
        >Guardados</button>
        <button
          onclick={() => (view = 'explore')}
          class="min-h-10 rounded-md px-4 text-fg-muted transition sm:min-h-9"
          class:bg-surface-3={view === 'explore'}
          class:text-fg={view === 'explore'}
          class:font-semibold={view === 'explore'}
        >Explorar</button>
      </div>
      <Button variant="primary" onclick={() => (creating = true)}><Plus size={16} /> Nueva playlist</Button>
    </div>
  </header>

  <label class="mb-6 flex min-h-11 items-center gap-2 rounded-lg border border-line bg-surface px-3 focus-within:border-accent">
    <Search size={16} class="text-fg-subtle" />
    <input
      bind:value={q}
      placeholder={view === 'saved' ? 'Buscar en tus guardados…' : 'Buscar en todo el catálogo…'}
      class="w-full bg-transparent text-sm focus:outline-none"
    />
  </label>

  {#if error}
    <ErrorState {error} />
  {:else if loading && albums.length === 0}
    <div class="card-grid">
      {#each Array(8) as _}
        <div><Skeleton class="aspect-square w-full" /><Skeleton class="mt-2 h-4 w-3/4" /><Skeleton class="mt-1.5 h-3 w-1/2" /></div>
      {/each}
    </div>
  {:else}
    <div class="card-grid">
      <!-- Favoritos: card fija siempre la primera en Guardados, sin búsqueda. -->
      {#if view === 'saved' && !q.trim()}
        <a href="/liked" class="group relative block">
          <div
            class="grid aspect-square w-full place-items-center rounded-xl bg-accent-soft text-accent transition group-hover:bg-surface-3"
          >
            <Heart size={48} fill="currentColor" />
          </div>
          <div class="mt-2 truncate text-sm font-semibold">Favoritos</div>
          <div class="truncate text-xs text-fg-subtle">
            {likedCount === null ? '…' : `${likedCount} ${likedCount === 1 ? 'canción' : 'canciones'}`}
          </div>
        </a>
      {/if}
      {#each albums as album (album.id)}
        <a href="/albums/{album.id}" class="group relative block">
          {#if album.cover_url}
            <img loading="lazy" decoding="async"
              src={coverSrc(album.cover_url, 384)}
              alt={album.title}
              class="aspect-square w-full rounded-xl object-cover transition group-hover:opacity-90"
            />
          {:else}
            <div class="grid aspect-square w-full place-items-center rounded-xl bg-surface-2 text-fg-subtle">
              {#if album.kind === 'playlist'}<ListMusic size={44} />{:else}<Disc3 size={44} />{/if}
            </div>
          {/if}
          <!-- Botón guardar/quitar -->
          <button
            onclick={(e) => toggleSave(e, album)}
            class="absolute right-1 top-1 grid size-10 place-items-center rounded-full bg-bg/80 transition hover:bg-surface"
            class:text-accent={album.is_saved}
            class:text-fg-muted={!album.is_saved}
            title={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
            aria-label={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
          >
            {#if album.is_saved}<BookmarkCheck size={16} />{:else}<Bookmark size={16} />{/if}
          </button>
          {#if album.kind === 'playlist'}
            <span class="absolute left-2 top-2 inline-flex items-center gap-1 rounded-md bg-bg/80 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-accent">
              <ListMusic size={12} /> playlist
            </span>
          {/if}
          <div class="mt-2 truncate text-sm font-semibold">{album.title}</div>
          <div class="truncate text-xs text-fg-subtle">
            {album.artist_name}{#if album.year} · {album.year}{/if}
          </div>
        </a>
      {/each}
    </div>
    {#if albums.length === 0}
      <p class="mt-6 text-center text-sm text-fg-muted">
        {#if q.trim()}
          Nada coincide con “{q.trim()}”.
        {:else if view === 'saved'}
          No tienes nada guardado. Ve a <button class="text-accent underline" onclick={() => (view = 'explore')}>Explorar</button> para guardar álbumes, o crea una playlist.
        {:else}
          Aún no hay álbumes en el servidor. Importa desde <a href="/import" class="text-accent underline">/import</a>.
        {/if}
      </p>
    {/if}
  {/if}
</div>

{#if creating}
  <NewAlbumDialog onclose={() => (creating = false)} oncreated={load} />
{/if}
