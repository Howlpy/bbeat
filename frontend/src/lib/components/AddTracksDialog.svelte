<script lang="ts">
  import { pushBack } from '$lib/backstack.svelte';
  import { coverSrc } from '$lib/cover';
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

  // Atrás de Android cierra este overlay.
  $effect(() => pushBack(() => onclose()));
</script>

<div
  class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center"
  onclick={onclose}
>
  <div
    class="flex h-[90vh] w-full max-w-2xl flex-col rounded-t-xl border border-line bg-surface shadow-xl sm:h-[80vh] sm:rounded-xl"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="flex flex-none items-center justify-between border-b border-line p-4">
      <div>
        <h2 class="text-lg font-semibold">Añadir pistas existentes</h2>
        <p class="text-xs text-fg-subtle">
          Selecciona pistas de tu biblioteca para añadirlas a este álbum.
        </p>
      </div>
      <button
        onclick={onclose}
        class="grid size-10 place-items-center rounded-lg text-fg-subtle hover:bg-surface-2"
        aria-label="Cerrar"
      ><X size={18} /></button>
    </header>

    <!-- Buscador -->
    <div class="flex-none border-b border-line p-3">
      <div class="relative">
        <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle" />
        <input
          type="search"
          bind:value={query}
          oninput={onQuery}
          placeholder="Buscar título, artista, álbum… (vacío = todas)"
          autofocus
          class="w-full rounded-lg border border-line bg-bg px-9 py-2 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
        />
        {#if loading}
          <Loader2 size={14} class="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-accent" />
        {:else if query}
          <button
            type="button"
            onclick={() => { query = ''; searchResults = []; }}
            class="absolute right-2 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-lg text-fg-subtle hover:bg-surface-2"
            aria-label="Limpiar"
          ><X size={12} /></button>
        {/if}
      </div>
    </div>

    {#if resultMsg}
      <div
        class="flex-none border-b border-line p-3 text-xs"
        class:bg-accent-soft={resultMsg.added > 0}
        class:text-accent={resultMsg.added > 0}
        class:bg-warning-soft={resultMsg.added === 0 && resultMsg.already > 0}
        class:text-warning={resultMsg.added === 0 && resultMsg.already > 0}
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
      <div class="flex flex-none items-center justify-between gap-2 border-b border-line bg-bg/50 px-3 py-2 text-xs">
        <label class="flex cursor-pointer items-center gap-2 text-fg-muted">
          <input
            type="checkbox"
            checked={allSelected}
            onchange={toggleAll}
            class="accent-accent"
          />
          Seleccionar todas ({results.length})
        </label>
        <span class="text-fg-subtle">
          {selected.size} seleccionadas
        </span>
      </div>
    {/if}

    <!-- Resultados -->
    <div class="flex-1 overflow-y-auto">
      {#if !initialLoaded}
        <p class="p-8 text-center text-sm text-fg-subtle">Cargando biblioteca…</p>
      {:else if results.length === 0}
        <p class="p-8 text-center text-sm text-fg-subtle">
          {query.trim()
            ? `Sin resultados para "${query}".`
            : 'Tu biblioteca está vacía o todas las pistas ya están en este álbum.'}
        </p>
      {:else}
        <ul class="divide-y divide-line-strong">
          {#each results as t (t.id)}
            {@const isSelected = selected.has(t.id)}
            <li>
              <button
                type="button"
                onclick={() => toggleSelect(t.id)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left transition"
                class:bg-accent-soft={isSelected}
                class:hover:bg-surface-2={!isSelected}
              >
                <span
                  class="grid size-5 flex-none place-items-center rounded-lg border"
                  class:border-accent={isSelected}
                  class:bg-accent={isSelected}
                  class:border-line-strong={!isSelected}
                >
                  {#if isSelected}
                    <Check size={12} class="text-accent-fg" />
                  {/if}
                </span>
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={coverSrc(t.cover_url, 96)} alt="" class="size-10 flex-none rounded-lg object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-fg-subtle">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="flex-none tabular-nums text-xs text-fg-subtle">
                  {formatDuration(t.duration_ms)}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Footer -->
    <footer class="flex flex-none items-center gap-2 border-t border-line p-3">
      <button
        type="button"
        onclick={onclose}
        class="rounded-lg border border-line px-4 py-2 text-sm transition hover:bg-surface-2 min-h-11 sm:min-h-10"
      >Cerrar</button>
      <button
        type="button"
        onclick={submit}
        disabled={saving || selected.size === 0}
        class="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50 min-h-11 sm:min-h-10"
      >
        {saving ? 'Añadiendo…' : `Añadir ${selected.size} ${selected.size === 1 ? 'pista' : 'pistas'}`}
      </button>
    </footer>
  </div>
</div>
