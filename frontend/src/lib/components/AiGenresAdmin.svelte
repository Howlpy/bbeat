<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { AlertTriangle, Check, Sparkles, Square, X } from 'lucide-svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import { api } from '$lib/api';
  import type { AiGenresStatus, AiSuggestion } from '$lib/aiGenres';
  import { GENRE_SLUGS, genreLabel } from '$lib/genres';

  const BATCH = 25;

  let status = $state<AiGenresStatus | null>(null);
  let error = $state<string | null>(null);
  let items = $state<AiSuggestion[]>([]);
  let reviewing = $state(false);
  let override = $state<Record<number, string>>({});
  let timer: ReturnType<typeof setInterval> | undefined;

  const run = $derived(status?.run);
  const toRun = $derived(Math.min(BATCH, status?.unclassified_artists ?? 0));

  async function refresh() {
    try {
      status = await api.aiGenresStatus();
      error = null;
      if (!status.run.running && timer) {
        clearInterval(timer);
        timer = undefined;
        if (reviewing) await loadItems();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  function poll() {
    if (!timer) timer = setInterval(refresh, 2000);
  }

  async function start() {
    try {
      await api.aiGenresRun(BATCH);
      await refresh();
      poll();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function loadItems() {
    items = (await api.aiSuggestions()).items;
  }

  async function toggleReview() {
    reviewing = !reviewing;
    if (reviewing) {
      try {
        await loadItems();
      } catch (e) {
        error = e instanceof Error ? e.message : String(e);
      }
    }
  }

  async function resolve(s: AiSuggestion, accept: boolean) {
    try {
      if (accept) {
        const g = override[s.id];
        await api.aiAccept(s.id, g && g !== s.genre ? g : undefined);
      } else {
        await api.aiReject(s.id);
      }
      items = items.filter((i) => i.id !== s.id);
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(async () => {
    await refresh();
    if (status?.run.running) poll();
  });
  onDestroy(() => timer && clearInterval(timer));
</script>

<section class="mb-8 rounded-xl border border-line bg-surface p-4">
  <h2 class="mb-1 flex items-center gap-2 text-sm font-semibold"><Sparkles size={15} /> Géneros con IA</h2>

  {#if error}
    <p class="mb-2 inline-flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 p-2 text-xs text-danger">
      <AlertTriangle size={14} /> {error}
    </p>
  {/if}

  {#if status}
    {#if !status.config.enabled}
      <p class="text-sm text-fg-muted">
        Desactivado. Define <code class="text-fg">BBEAT_AI_PROVIDER</code> y la clave en <code class="text-fg">backend/.env</code>
        para clasificar artistas con un modelo de IA (ver README).
      </p>
    {:else}
      <dl class="mb-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt class="text-fg-subtle">Modelo</dt>
        <dd>{status.config.provider} · {status.config.model}</dd>
        <dt class="text-fg-subtle">Búsqueda web</dt>
        <dd>{status.config.search_configured ? status.config.search_provider : 'sin configurar'}</dd>
        <dt class="text-fg-subtle">Confianza mínima</dt>
        <dd>{status.config.min_confidence} · {status.config.rpm} peticiones/min</dd>
        <dt class="text-fg-subtle">Pistas sin género</dt>
        <dd>{status.tracks_without_genre}</dd>
        <dt class="text-fg-subtle">Artistas sin clasificar</dt>
        <dd>{status.unclassified_artists}</dd>
        <dt class="text-fg-subtle">Pendientes de revisar</dt>
        <dd>{status.pending_suggestions}</dd>
      </dl>

      <div class="flex flex-wrap gap-2">
        <Button onclick={start} disabled={run?.running || toRun === 0}>
          <Sparkles size={16} /> Clasificar ahora ({toRun} artistas)
        </Button>
        {#if run?.running}
          <Button variant="ghost" onclick={() => api.aiGenresStop()}><Square size={14} /> Parar</Button>
        {/if}
        <Button onclick={toggleReview} disabled={!status.pending_suggestions && !reviewing}>
          {reviewing ? 'Ocultar sugerencias' : `Revisar sugerencias (${status.pending_suggestions})`}
        </Button>
      </div>

      {#if run && (run.running || run.finished_at)}
        <p class="mt-3 text-sm {run.quota_exceeded ? 'text-warning' : 'text-fg-muted'}">
          {#if run.running}
            Clasificando… {run.done}{run.total ? ` / ${run.total}` : ''} artistas
            {#if run.message}· {run.message}{/if}
          {:else}
            {run.message} {run.done} artistas: {run.applied} aplicados, {run.pending} a revisión, {run.skipped} sin decidir.
          {/if}
        </p>
        {#if run.running && run.total}
          <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3">
            <div class="h-full bg-accent transition-all" style="width: {Math.min(100, (100 * run.done) / run.total)}%"></div>
          </div>
        {/if}
      {/if}

      {#if reviewing}
        {#if items.length === 0}
          <p class="mt-3 text-sm text-fg-muted">No hay sugerencias pendientes.</p>
        {:else}
          <ul class="mt-3 divide-y divide-line overflow-hidden rounded-lg border border-line">
            {#each items as s (s.id)}
              <li class="flex flex-wrap items-center gap-2 p-3">
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm font-medium">
                    {s.artist_name}{#if s.track_title}<span class="font-normal text-fg-muted"> · {s.track_title}</span>{/if}
                  </div>
                  <div class="text-xs text-fg-subtle">
                    {genreLabel(s.previous_genre)} → {s.genre_name} · confianza {Math.round(s.confidence * 100)}%
                  </div>
                  {#if s.reason}<div class="text-xs text-fg-muted">{s.reason}</div>{/if}
                </div>
                <select
                  value={override[s.id] ?? s.genre}
                  onchange={(e) => (override[s.id] = e.currentTarget.value)}
                  aria-label="Género"
                  class="min-h-11 rounded-lg border border-line bg-surface px-2 text-sm focus:border-accent focus:outline-none sm:min-h-10"
                >
                  {#each GENRE_SLUGS as g}<option value={g}>{genreLabel(g)}</option>{/each}
                </select>
                <button
                  onclick={() => resolve(s, true)}
                  class="inline-flex items-center gap-1 rounded-lg bg-accent px-3.5 py-2 text-xs font-semibold text-accent-fg transition hover:bg-accent-hover min-h-11 sm:min-h-10"
                ><Check size={13} /> Aceptar</button>
                <button
                  onclick={() => resolve(s, false)}
                  class="inline-flex items-center gap-1 rounded-lg border border-line px-3.5 py-2 text-xs transition hover:bg-surface-2 min-h-11 sm:min-h-10"
                ><X size={13} /> Rechazar</button>
              </li>
            {/each}
          </ul>
        {/if}
      {/if}
    {/if}
  {/if}
</section>
