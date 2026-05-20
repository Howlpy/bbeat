<script lang="ts">
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
  let results = $state<Track[]>([]);
  let loading = $state(false);
  let searched = $state(false);
  let selected = $state<Set<number>>(new Set());
  let saving = $state(false);
  let resultMsg = $state<{ added: number; already: number; denied: number } | null>(null);
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function runSearch(q: string) {
    if (!q.trim()) {
      results = [];
      searched = false;
      return;
    }
    loading = true;
    try {
      const r = await api.search(q.trim(), 50);
      // Filtrar las que ya están en el álbum
      results = r.items.filter((t) => !excludeIds.includes(t.id));
      searched = true;
    } catch {
      results = [];
    } finally {
      loading = false;
    }
  }

  function onQuery() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => runSearch(query), 250);
  }

  function toggleSelect(id: number) {
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    selected = new Set(selected); // trigger reactivity
  }

  function toggleAll() {
    if (selected.size === results.length) {
      selected = new Set();
    } else {
      selected = new Set(results.map((r) => r.id));
    }
  }

  async function submit() {
    if (selected.size === 0 || saving) return;
    saving = true;
    try {
      const r = await api.addTracksToAlbum(albumId, [...selected]);
      resultMsg = r;
      if (r.added > 0) {
        onadded?.(r.added);
        // Reset y dejar dialog abierto para añadir más
        selected = new Set();
        await runSearch(query);
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
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
          Busca en tu biblioteca y selecciona las que quieras añadir a este álbum.
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
          placeholder="Buscar título, artista, álbum…"
          autofocus
          class="w-full rounded border border-slate-800 bg-slate-950 px-9 py-2 text-sm placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
        />
        {#if loading}
          <Loader2 size={14} class="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-sky-400" />
        {/if}
      </div>
    </div>

    {#if resultMsg && resultMsg.added > 0}
      <div class="flex-none border-b border-slate-800 bg-cyan-950/30 p-3 text-xs text-cyan-300">
        Añadidas {resultMsg.added}
        {resultMsg.already > 0 ? `· ${resultMsg.already} ya estaban` : ''}
        {resultMsg.denied > 0 ? `· ${resultMsg.denied} sin acceso` : ''}
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
      {#if !searched && !loading}
        <p class="p-8 text-center text-sm text-slate-500">
          Empieza a escribir para buscar pistas en tu biblioteca.
        </p>
      {:else if loading && results.length === 0}
        <p class="p-8 text-center text-sm text-slate-500">Buscando…</p>
      {:else if results.length === 0}
        <p class="p-8 text-center text-sm text-slate-500">
          Sin resultados para "{query}".
          <br />
          <span class="text-xs text-slate-600">
            Las que ya están en este álbum se ocultan.
          </span>
        </p>
      {:else}
        <ul class="divide-y divide-slate-900">
          {#each results as t (t.id)}
            {@const isSelected = selected.has(t.id)}
            <li>
              <button
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
        onclick={onclose}
        class="rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-800"
      >Cerrar</button>
      <button
        onclick={submit}
        disabled={saving || selected.size === 0}
        class="flex-1 rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
      >
        {saving ? 'Añadiendo…' : `Añadir ${selected.size} ${selected.size === 1 ? 'pista' : 'pistas'}`}
      </button>
    </footer>
  </div>
</div>
