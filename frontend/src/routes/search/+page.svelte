<script lang="ts">
  import { X, Search } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

  let query = $state('');
  let tracks = $state<Track[]>([]);
  let searching = $state(false);
  let searched = $state(false);
  let error = $state<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  // Descarta respuestas viejas si el usuario sigue escribiendo.
  let seq = 0;

  async function run(q: string) {
    const term = q.trim();
    const mine = ++seq;
    if (!term) {
      tracks = [];
      searched = false;
      searching = false;
      error = null;
      return;
    }
    searching = true;
    try {
      const r = await api.search(term);
      if (mine !== seq) return;
      tracks = r.items;
      searched = true;
      error = null;
    } catch (e) {
      if (mine !== seq) return;
      error = e instanceof Error ? e.message : String(e);
    } finally {
      if (mine === seq) searching = false;
    }
  }

  function onInput() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => run(query), 250);
  }

  function clear() {
    query = '';
    run('');
  }
</script>

<div class="page-narrow">
  <h1 class="page-title mb-4">Buscar</h1>

  <div class="relative mb-5">
    <input
      type="search"
      bind:value={query}
      oninput={onInput}
      placeholder="Título, artista, álbum…"
      class="min-h-12 w-full rounded-lg border border-line bg-surface px-3 pr-11 text-base placeholder:text-fg-subtle focus:border-accent focus:outline-none"
    />
    {#if searching}
      <span class="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-accent">…</span>
    {:else if query}
      <button
        onclick={clear}
        class="absolute right-0 top-1/2 grid size-11 -translate-y-1/2 place-items-center rounded-lg text-fg-subtle hover:text-fg"
        aria-label="Limpiar"
      ><X size={16} /></button>
    {/if}
  </div>

  {#if error}
    <ErrorState {error} />
  {:else if !searched}
    <EmptyState icon={Search} title="Busca en tu música" text="Escribe el nombre de una canción, artista o álbum." />
  {:else if tracks.length === 0}
    <p class="rounded-xl border border-line bg-surface p-4 text-sm text-fg-muted">Sin resultados.</p>
  {:else}
    <TrackList {tracks} onchanged={() => run(query)} />
  {/if}
</div>
