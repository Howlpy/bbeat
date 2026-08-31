<script lang="ts">
  import { onMount } from 'svelte';
  import { X, Shuffle, Heart, ChevronLeft, Music2, Tag } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
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

  onMount(loadGenres);
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
    <div class="flex min-w-0 items-center gap-2">
      {#if selected !== null}
        <button
          onclick={volver}
          class="-ml-1 grid size-8 flex-none place-items-center rounded-full text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
          aria-label="Volver a los géneros"
        ><ChevronLeft size={20} /></button>
      {/if}
      <h1 class="truncate text-2xl font-bold">{nombreVista}</h1>
    </div>
    <div class="flex items-center gap-3">
      <a
        href="/liked"
        class="inline-flex items-center gap-1.5 text-xs text-slate-400 transition hover:text-cyan-400"
      ><Heart size={14} /> Favoritos</a>
      <span class="text-xs text-slate-500">
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
      class="mb-3 flex w-full items-center gap-4 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-cyan-500/15 to-slate-900/40 px-4 py-4 text-left transition hover:border-cyan-400 hover:from-cyan-500/25"
    >
      <span class="grid size-11 flex-none place-items-center rounded-lg bg-cyan-500 text-slate-950">
        <Music2 size={22} />
      </span>
      <span class="min-w-0 flex-1">
        <span class="block font-semibold">Todas las canciones</span>
        <span class="block text-xs text-slate-400">{libraryTotal} pistas en la biblioteca</span>
      </span>
    </button>

    {#if genres.length > 0}
      <h2 class="mb-2 mt-5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
        <Tag size={13} /> Por género
      </h2>
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {#each genres as g (g.genre)}
          <button
            onclick={() => abrir(g.genre)}
            class="group rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-left transition hover:border-cyan-500/60 hover:bg-slate-900"
          >
            <span class="block truncate font-medium transition group-hover:text-cyan-400">
              {genreLabel(g.genre)}
            </span>
            <span class="mt-0.5 block font-mono text-xs text-slate-500">{g.count}</span>
            <!-- Barra proporcional: de un vistazo se ve qué pesa en tu biblioteca -->
            <span class="mt-2 block h-1 overflow-hidden rounded-full bg-slate-800">
              <span
                class="block h-full rounded-full bg-cyan-500/70 transition-all group-hover:bg-cyan-400"
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
          class="mt-2 flex w-full items-center gap-3 rounded-xl border border-dashed border-slate-700 bg-slate-900/40 px-3 py-2.5 text-left transition hover:border-cyan-500/60 hover:bg-slate-900"
        >
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-slate-300">Sin género</span>
            <span class="block text-xs text-slate-500">
              {withoutGenre} {withoutGenre === 1 ? 'canción por clasificar' : 'canciones por clasificar'} · ponles género con ⋮ → Editar
            </span>
          </span>
          <span class="flex-none font-mono text-xs text-slate-500">{withoutGenre}</span>
        </button>
      {/if}
    {:else}
      <p class="mt-4 rounded-md border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
        Todavía no hay géneros en la biblioteca.
      </p>
    {/if}
  {:else}
    {#if tracks.length > 0}
      <button
        onclick={shuffleAll}
        class="mb-4 inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
      >
        <Shuffle size={16} /> Reproducir aleatorio
      </button>
    {/if}

    <div class="mb-4 flex items-center gap-2">
      <div class="relative min-w-0 flex-1">
        <input
          type="search"
          bind:value={query}
          oninput={onQueryChange}
          placeholder={selected === '__all__' ? 'Buscar título, artista, álbum…' : `Buscar en ${etiqueta(selected)}…`}
          class="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 pr-9 text-sm placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
        />
        {#if searching}
          <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-sky-400">…</span>
        {:else if query}
          <button
            onclick={() => { query = ''; doSearch(''); }}
            class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:bg-slate-800"
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
      <p class="text-red-400">{error}</p>
    {:else if loading && tracks.length === 0}
      <ul class="divide-y divide-slate-900">
        {#each Array(8) as _, i (i)}
          <li class="flex items-center gap-3 px-2 py-2">
            <div class="size-10 flex-none animate-pulse rounded bg-slate-800"></div>
            <div class="flex-1 space-y-2">
              <div class="h-3 w-1/2 animate-pulse rounded bg-slate-800"></div>
              <div class="h-2.5 w-1/3 animate-pulse rounded bg-slate-800"></div>
            </div>
          </li>
        {/each}
      </ul>
    {:else if tracks.length === 0}
      <p class="rounded-md border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400">
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
