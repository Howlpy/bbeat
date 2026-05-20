<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { api, formatDuration, type Job } from '$lib/api';

  let url = $state('');
  let submitting = $state(false);
  let lastResult = $state<string | null>(null);
  let error = $state<string | null>(null);

  let jobs = $state<Job[]>([]);
  let pollTimer: ReturnType<typeof setTimeout> | null = null;

  const hasActiveJobs = $derived(jobs.some((j) => j.status === 'pending' || j.status === 'running'));

  async function refresh() {
    try {
      const r = await api.listJobs(100);
      jobs = r.items;
    } catch (e) {
      console.warn('listJobs failed', e);
    }
  }

  function schedule() {
    if (pollTimer) clearTimeout(pollTimer);
    const ms = hasActiveJobs ? 1500 : 5000;
    pollTimer = setTimeout(async () => {
      await refresh();
      schedule();
    }, ms);
  }

  async function submit() {
    if (!url.trim() || submitting) return;
    submitting = true;
    error = null;
    lastResult = null;
    try {
      const r = await api.ingest(url.trim());
      const skipped = r.skipped_track_ids.length;
      lastResult = `${r.kind === 'track' ? 'Pista' : r.kind === 'album' ? 'Álbum' : 'Playlist'}: "${r.name}". ${r.created_job_ids.length} jobs nuevos${skipped ? `, ${skipped} duplicados ignorados` : ''}.`;
      url = '';
      await refresh();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      submitting = false;
    }
  }

  async function retry(id: number) {
    await api.retryJob(id);
    await refresh();
  }

  async function remove(id: number) {
    await api.deleteJob(id);
    await refresh();
  }

  onMount(async () => {
    await refresh();
    schedule();
  });

  onDestroy(() => {
    if (pollTimer) clearTimeout(pollTimer);
  });

  function statusColor(s: Job['status']): string {
    if (s === 'done') return 'text-emerald-400';
    if (s === 'running') return 'text-sky-400';
    if (s === 'failed') return 'text-red-400';
    return 'text-neutral-400';
  }

  function statusLabel(s: Job['status']): string {
    return { pending: '⏱ en cola', running: '⟳ descargando', done: '✓ listo', failed: '✗ fallo' }[s];
  }
</script>

<div class="mx-auto max-w-2xl px-4 pt-6">
  <h1 class="mb-2 text-2xl font-bold">Importar desde Spotify</h1>
  <p class="mb-4 text-sm text-neutral-500">
    Pega una URL de track, álbum o playlist. Bbeat resolverá la metadata y
    descargará el audio.
  </p>

  <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="flex flex-col gap-2 sm:flex-row">
    <input
      type="url"
      bind:value={url}
      placeholder="https://open.spotify.com/track/..."
      autocomplete="off"
      inputmode="url"
      class="flex-1 rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm placeholder:text-neutral-600 focus:border-emerald-500 focus:outline-none"
    />
    <button
      type="submit"
      disabled={submitting || !url.trim()}
      class="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-emerald-400 disabled:opacity-50"
    >
      {submitting ? 'Resolviendo…' : 'Importar'}
    </button>
  </form>

  {#if error}
    <p class="mt-3 rounded-md border border-red-900/50 bg-red-950/40 p-3 text-sm text-red-300">⚠️ {error}</p>
  {/if}
  {#if lastResult}
    <p class="mt-3 rounded-md border border-emerald-900/50 bg-emerald-950/30 p-3 text-sm text-emerald-200">{lastResult}</p>
  {/if}

  <section class="mt-8">
    <header class="mb-3 flex items-baseline justify-between">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-neutral-500">Cola de jobs</h2>
      {#if hasActiveJobs}
        <span class="text-xs text-sky-400">{jobs.filter((j) => j.status === 'running' || j.status === 'pending').length} activos</span>
      {/if}
    </header>

    {#if jobs.length === 0}
      <p class="text-sm text-neutral-500">Aún no has importado nada.</p>
    {:else}
      <ul class="divide-y divide-neutral-900 rounded-md border border-neutral-900">
        {#each jobs as job}
          <li class="flex items-center gap-3 p-3">
            {#if job.cover_url}
              <img src={job.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
            {:else}
              <div class="size-10 flex-none rounded bg-neutral-800"></div>
            {/if}
            <div class="min-w-0 flex-1">
              <div class="flex items-baseline gap-2">
                <span class="truncate text-sm font-medium">{job.title || job.spotify_track_id}</span>
                <span class="flex-none text-xs {statusColor(job.status)}">{statusLabel(job.status)}</span>
              </div>
              <div class="truncate text-xs text-neutral-500">
                {job.artist}{#if job.album} · {job.album}{/if}
                {#if job.backend_used} · {job.backend_used}{/if}
                {#if job.duration_ms} · {formatDuration(job.duration_ms)}{/if}
              </div>
              {#if job.error}
                <div class="mt-1 truncate text-xs text-red-400" title={job.error}>{job.error}</div>
              {/if}
            </div>
            <div class="flex flex-none gap-1">
              {#if job.status === 'failed'}
                <button
                  onclick={() => retry(job.id)}
                  class="rounded border border-neutral-800 px-2 py-1 text-xs hover:bg-neutral-900"
                  title="Reintentar"
                >↻</button>
              {/if}
              {#if job.status !== 'running'}
                <button
                  onclick={() => remove(job.id)}
                  class="rounded border border-neutral-800 px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-900 hover:text-red-400"
                  title="Eliminar de la cola"
                >×</button>
              {/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>
