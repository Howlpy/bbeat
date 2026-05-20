<script lang="ts">
  import { onMount } from 'svelte';
  import { Check, Loader2, Music2, Search, X } from 'lucide-svelte';
  import { api, formatDuration, type Track } from '$lib/api';

  let {
    albumId,
    excludeIds = [],
    onclose,
    onadded
  }: {
    albumId: number;
    excludeIds?: number[];
    onclose: () => void;
    onadded?: (count: number) => void;
  } = $props();

  let query = $state('');
  let allTracks = $state<Track[]>([]);          // toda la biblioteca visible
  let searchResults = $state<Track[]>([]);      // resultados cuando hay query
  let loading = $state(false);
  let initialLoaded = $state(false);
  let selected = $state<Set<number>>(new Set());
  let saving = $state(false);
  let resultMsg = $state<{ added: number; already: number; denied: number } | null>(null);
  let timer: ReturnType<typeof setTimeout> | null = null;

  const excludeSet = $derived(new Set(excludeIds));

  // Tracks a mostrar: si hay query usa search results, si no, todos.
  const results = $derived.by(() => {
    const source = query.trim() ? searchResults : allTracks;
    return source.filter((t) => !excludeSet.has(t.id));
  });

  onMount(async () => {
    loading = true;
    try {
      const r = await api.tracks({ limit: 500 });
      allTracks = r.items;
    } catch (e) {
      console.warn('load all tracks failed', e);
    } finally {
      loading = false;
      initialLoaded = true;
    }
  });

  async function runSearch(q: string) {
    if (!q.trim()) {
      searchResults = [];
      return;
    }
    loading = true;
    try {
      const r = await api.search(q.trim(), 100);
      searchResults = r.items;
    } catch {
      searchResults = [];
    } finally {
      loading = false;
    }
  }

  function onQuery() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => runSearch(query), 250);
  }

  function toggleSelect(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    selected = next;
  }

  function toggleAll() {
    if (selected.size === results.length && results.length > 0) {
      selected = new Set();
    } else {
      selected = new Set(results.map((r) => r.id));
    }
  }

  async function submit() {
    if (selected.size === 0 || saving) return;
    saving = true;
    resultMsg = null;
    try {
      const ids = Array.from(selected);
      console.log('[bbeat] addTracksToAlbum', albumId, ids);
      const r = await api.addTracksToAlbum(albumId, ids);
      console.log('[bbeat] result', r);
      resultMsg = r;
      if (r.added > 0) {
        onadded?.(r.added);
        selected = new Set();
        // Refrescar el listado: las pistas añadidas pasan a estar en excludeIds
        // Pero excludeIds es prop; el caller hace load() que actualiza tracks
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[bbeat] addTracksToAlbum failed', msg);
      alert('Error añadiendo pistas: ' + msg);
    } finally {
      saving = false;
    }
  }

  const allSelected = $derived(results.length > 0 && selected.size === results.length);
</script>

<div
  class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center"
  onclick={onclose}
>
  <div
    class="flex h-[90vh] w-full max-w-2xl flex-col rounded-t-lg border border-slate-800 bg-slate-900 shadow-xl sm:h-[80vh] sm:rounded"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="flex flex-none items-center justify-between border-b border-slate-800 p-4">
      <div>
        <h2 class="text-lg font-semibold">Añadir pistas existentes</h2>
        <p class="text-xs text-slate-500">
          Selecciona pistas de tu biblioteca para añadirlas a este álbum.
        </p>
      </div>
      <button
        onclick={onclose}
        class="grid size-8 place-items-center rounded text-slate-500 hover:bg-slate-800"
        aria-label="Cerrar"
      ><X size={18} /></button>
    </header>

    <!-- Buscador -->
    <div class="flex-none border-b border-slate-800 p-3">
      <div class="relative">
        <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
        <input
          type="search"
          bind:value={query}
          oninput={onQuery}
          placeholder="Buscar título, artista, álbum… (vacío = todas)"
          autofocus
          class="w-full rounded border border-slate-800 bg-slate-950 px-9 py-2 text-sm placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
        />
        {#if loading}
          <Loader2 size={14} class="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-sky-400" />
        {:else if query}
          <button
            type="button"
            onclick={() => { query = ''; searchResults = []; }}
            class="absolute right-2 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-slate-500 hover:bg-slate-800"
            aria-label="Limpiar"
          ><X size={12} /></button>
        {/if}
      </div>
    </div>

    {#if resultMsg}
      <div
        class="flex-none border-b border-slate-800 p-3 text-xs"
        class:bg-cyan-950={resultMsg.added > 0}
        class:text-cyan-300={resultMsg.added > 0}
        class:bg-amber-950={resultMsg.added === 0 && resultMsg.already > 0}
        class:text-amber-300={resultMsg.added === 0 && resultMsg.already > 0}
      >
        {#if resultMsg.added > 0}
          Añadidas {resultMsg.added}{resultMsg.already > 0 ? ` · ${resultMsg.already} ya estaban` : ''}{resultMsg.denied > 0 ? ` · ${resultMsg.denied} sin acceso` : ''}.
        {:else if resultMsg.already > 0}
          Esas pistas ya estaban en el álbum.
        {:else}
          Sin cambios.
        {/if}
      </div>
    {/if}

    <!-- Acción masiva -->
    {#if results.length > 0}
      <div class="flex flex-none items-center justify-between gap-2 border-b border-slate-800 bg-slate-950/50 px-3 py-2 text-xs">
        <label class="flex cursor-pointer items-center gap-2 text-slate-400">
          <input
            type="checkbox"
            checked={allSelected}
            onchange={toggleAll}
            class="accent-cyan-400"
          />
          Seleccionar todas ({results.length})
        </label>
        <span class="text-slate-500">
          {selected.size} seleccionadas
        </span>
      </div>
    {/if}

    <!-- Resultados -->
    <div class="flex-1 overflow-y-auto">
      {#if !initialLoaded}
        <p class="p-8 text-center text-sm text-slate-500">Cargando biblioteca…</p>
      {:else if results.length === 0}
        <p class="p-8 text-center text-sm text-slate-500">
          {query.trim()
            ? `Sin resultados para "${query}".`
            : 'Tu biblioteca está vacía o todas las pistas ya están en este álbum.'}
        </p>
      {:else}
        <ul class="divide-y divide-slate-900">
          {#each results as t (t.id)}
            {@const isSelected = selected.has(t.id)}
            <li>
              <button
                type="button"
                onclick={() => toggleSelect(t.id)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left transition"
                class:bg-cyan-950={isSelected}
                class:hover:bg-slate-800={!isSelected}
              >
                <span
                  class="grid size-5 flex-none place-items-center rounded border"
                  class:border-cyan-400={isSelected}
                  class:bg-cyan-400={isSelected}
                  class:border-slate-700={!isSelected}
                >
                  {#if isSelected}
                    <Check size={12} class="text-slate-950" />
                  {/if}
                </span>
                {#if t.cover_url}
                  <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-slate-500">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="flex-none font-mono text-xs text-slate-500">
                  {formatDuration(t.duration_ms)}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Footer -->
    <footer class="flex flex-none items-center gap-2 border-t border-slate-800 p-3">
      <button
        type="button"
        onclick={onclose}
        class="rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-800"
      >Cerrar</button>
      <button
        type="button"
        onclick={submit}
        disabled={saving || selected.size === 0}
        class="flex-1 rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {saving ? 'Añadiendo…' : `Añadir ${selected.size} ${selected.size === 1 ? 'pista' : 'pistas'}`}
      </button>
    </footer>
  </div>
</div>
