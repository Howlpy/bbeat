<script lang="ts">
  import { pushBack } from '$lib/backstack.svelte';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import { X, Shuffle, Heart, ChevronLeft, Music2, Tag } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, type TrackSort } from '$lib/sort';
  import { genreLabel, SIN_GENERO } from '$lib/genres';

  type GenreRow = { genre: string; count: number };

  let tracks = $state<Track[]>([]);
  let total = $state(0);
  let error = $state<string | null>(null);
  let query = $state('');
  let searching = $state(false);
  let loading = $state(true);
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  let sort = $state<TrackSort>('original');
  const visibleTracks = $derived(sortTracks(tracks, sort));

  let genres = $state<GenreRow[]>([]);
  let libraryTotal = $state(0);
  let withoutGenre = $state(0);
  /** null = aún no has elegido, se ven las tarjetas. */
  let selected = $state<string | null>(null);

  // Los géneros se cuentan en el servidor: aquí solo hay una página de pistas,
  // así que contar sobre `tracks` daría cifras que no cuadran con la biblioteca.
  const nombreVista = $derived(selected === null ? 'Canciones' : etiqueta(selected));

  function etiqueta(g: string): string {
    return g === '__all__' ? 'Todas las canciones' : genreLabel(g);
  }

  async function loadGenres() {
    try {
      const r = await api.genres();
      genres = r.items;
      libraryTotal = r.total;
      withoutGenre = r.without_genre;
    } catch {
      // Sin géneros la página sigue sirviendo: se entra por "todas".
      genres = [];
    }
  }

  async function load(genre?: string) {
    loading = true;
    try {
      const res = await api.tracks({ limit: 500, ...(genre ? { genre } : {}) });
      tracks = res.items;
      total = res.total;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function abrir(g: string) {
    selected = g;
    query = '';
    load(g === '__all__' ? undefined : g);
    if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
  }

  // Atrás de Android: de un género a la lista de géneros.
  $effect(() => {
    if (selected !== null) return pushBack(volver);
  });

  function volver() {
    selected = null;
    query = '';
    tracks = [];
  }

  async function doSearch(q: string) {
    if (!q.trim()) {
      await load(selected && selected !== '__all__' ? selected : undefined);
      return;
    }
    searching = true;
    try {
      const r = await api.search(q.trim());
      // La búsqueda va contra toda la biblioteca; si estabas dentro de un
      // género, se filtra aquí para no sacarte de él sin avisar.
      const items =
        selected && selected !== '__all__'
          ? r.items.filter((t) =>
              selected === SIN_GENERO
                ? !(t.genre || '').trim()
                : (t.genre || '').toLowerCase() === selected
            )
          : r.items;
      tracks = items;
      total = items.length;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      searching = false;
    }
  }

  function onQueryChange() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => doSearch(query), 250);
  }

  function shuffleAll() {
    if (tracks.length) player.playShuffled(tracks);
  }

  onMount(() => {
    loadGenres();
    // Al volver la red, reintenta lo que esté a medias o con error.
    return onReconnect(() => {
      loadGenres();
      if (selected !== null && (error || tracks.length === 0)) load(selected === '__all__' ? undefined : selected);
    });
  });
</script>

<div class="page-narrow">
  <header class="mb-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
    <div class="flex min-w-0 items-center gap-2">
      {#if selected !== null}
        <button
          onclick={volver}
          class="-ml-1 grid size-10 flex-none place-items-center rounded-full text-fg-muted transition hover:bg-surface-2 hover:text-fg"
          aria-label="Volver a los géneros"
        ><ChevronLeft size={20} /></button>
      {/if}
      <h1 class="page-title truncate">{nombreVista}</h1>
    </div>
    <div class="flex items-center gap-3">
      <a
        href="/liked"
        class="inline-flex min-h-10 items-center gap-1.5 text-sm text-fg-muted transition hover:text-accent"
      ><Heart size={14} /> Favoritos</a>
      <span class="text-sm tabular-nums text-fg-subtle">
        {#if selected === null}
          {libraryTotal} en biblioteca
        {:else}
          {total} {query ? 'resultados' : 'canciones'}
        {/if}
      </span>
    </div>
  </header>

  {#if selected === null}
    <!-- Portada de la sección: por dónde entrar a las canciones -->
    <button
      onclick={() => abrir('__all__')}
      class="mb-3 flex w-full items-center gap-4 rounded-xl border border-accent/40 bg-accent-soft px-4 py-4 text-left transition hover:border-accent"
    >
      <span class="grid size-11 flex-none place-items-center rounded-lg bg-accent text-accent-fg">
        <Music2 size={22} />
      </span>
      <span class="min-w-0 flex-1">
        <span class="block font-semibold">Todas las canciones</span>
        <span class="block text-sm text-fg-muted">{libraryTotal} pistas en la biblioteca</span>
      </span>
    </button>

    {#if genres.length > 0}
      <h2 class="section-title mb-3 mt-8">
        <Tag size={13} /> Por género
      </h2>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {#each genres as g (g.genre)}
          <button
            onclick={() => abrir(g.genre)}
            class="group rounded-xl border border-line bg-surface p-4 text-left transition hover:border-line-strong hover:bg-surface-2"
          >
            <span class="block truncate font-medium transition group-hover:text-accent">
              {genreLabel(g.genre)}
            </span>
            <span class="mt-0.5 block text-sm tabular-nums text-fg-subtle">{g.count}</span>
            <!-- Barra proporcional: de un vistazo se ve qué pesa en tu biblioteca -->
            <span class="mt-3 block h-1 overflow-hidden rounded-full bg-surface-3">
              <span
                class="block h-full rounded-full bg-accent transition-all"
                style:width="{Math.max(4, (g.count / genres[0].count) * 100)}%"
              ></span>
            </span>
          </button>
        {/each}
      </div>
      {#if withoutGenre > 0}
        <!-- Entrar a las pistas sin clasificar es lo que permite arreglarlas:
             desde la lista se les pone género a mano con ⋮ → Editar. -->
        <button
          onclick={() => abrir(SIN_GENERO)}
          class="mt-3 flex min-h-14 w-full items-center gap-3 rounded-xl border border-dashed border-line-strong px-4 py-2.5 text-left transition hover:bg-surface"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-fg-muted">Sin género</span>
            <span class="block text-xs text-fg-subtle">
              {withoutGenre} {withoutGenre === 1 ? 'canción por clasificar' : 'canciones por clasificar'} · ponles género con ⋮ → Editar
            </span>
          </span>
          <span class="flex-none text-sm tabular-nums text-fg-subtle">{withoutGenre}</span>
        </button>
      {/if}
    {:else}
      <p class="mt-4 rounded-xl border border-line bg-surface p-4 text-sm text-fg-muted">
        Todavía no hay géneros en la biblioteca.
      </p>
    {/if}
  {:else}
    {#if tracks.length > 0}
      <Button variant="primary" onclick={shuffleAll} class="mb-4"><Shuffle size={16} /> Reproducir aleatorio</Button>
    {/if}

    <div class="mb-4 flex items-center gap-2">
      <div class="relative min-w-0 flex-1">
        <input
          type="search"
          bind:value={query}
          oninput={onQueryChange}
          placeholder={selected === '__all__' ? 'Buscar título, artista, álbum…' : `Buscar en ${etiqueta(selected)}…`}
          class="min-h-11 w-full rounded-lg border border-line bg-surface px-3 pr-11 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        {#if searching}
          <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-accent">…</span>
        {:else if query}
          <button
            onclick={() => { query = ''; doSearch(''); }}
            class="absolute right-0 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-fg-subtle hover:text-fg"
            aria-label="Limpiar"
          ><X size={14} /></button>
        {/if}
      </div>
      <SortSelect
        prefKey={selected === '__all__' ? 'sort:library' : `sort:genre:${selected}`}
        bind:value={sort}
        originalLabel="Orden de la biblioteca"
      />
    </div>

    {#if error}
      <ErrorState {error} />
    {:else if loading && tracks.length === 0}
      <ul class="divide-y divide-line">
        {#each Array(8) as _, i (i)}
          <li class="flex items-center gap-3 px-2 py-2">
            <div class="size-10 flex-none animate-pulse rounded-lg bg-surface-2"></div>
            <div class="flex-1 space-y-2">
              <div class="h-3 w-1/2 animate-pulse rounded-lg bg-surface-2"></div>
              <div class="h-2.5 w-1/3 animate-pulse rounded-lg bg-surface-2"></div>
            </div>
          </li>
        {/each}
      </ul>
    {:else if tracks.length === 0}
      <p class="rounded-xl border border-line bg-surface p-4 text-sm text-fg-muted">
        {query ? 'Sin resultados.' : 'Aquí no hay ninguna canción todavía.'}
      </p>
    {:else}
      <TrackList
        tracks={visibleTracks}
        showAlbum={sort === 'album'}
        showGenre={selected === '__all__' && sort === 'genre'}
        onchanged={() => load(selected === '__all__' ? undefined : selected ?? undefined)}
      />
    {/if}
  {/if}
</div>
