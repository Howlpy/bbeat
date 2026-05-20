<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    formatDuration,
    type Album,
    type IngestPreview,
    type IngestOverrides,
    type Job,
    type Source,
    type SpotifyAuthStatus
  } from '$lib/api';
  import { jobs } from '$lib/jobs.svelte';

  let url = $state('');
  let busy = $state(false);
  let preview = $state<IngestPreview | null>(null);
  let previewError = $state<string | null>(null);
  let lastImportMsg = $state<string | null>(null);
  let auth = $state<SpotifyAuthStatus | null>(null);
  let albums = $state<Album[]>([]);
  let expanded = $state<Record<string, boolean>>({});

  // Overrides editables (rellenan defaults desde el preview)
  let ovMode = $state<'new' | 'existing'>('new');
  let ovAlbum = $state('');
  let ovArtist = $state('');
  let ovYear = $state<string>('');
  let ovTargetAlbumId = $state<number | null>(null);

  // Detección rápida de la fuente desde el frontend (sin ir al backend)
  function detectSource(u: string): Source {
    const s = (u || '').trim();
    if (!s) return 'unknown';
    if (/^(spotify:|https?:\/\/open\.spotify\.com\/)/i.test(s)) return 'spotify';
    if (/^https?:\/\/(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)\//i.test(s)) return 'youtube';
    if (/^https?:\/\/(?:www\.|m\.|on\.)?soundcloud\.com\//i.test(s)) return 'soundcloud';
    return 'unknown';
  }

  const detectedSource = $derived(detectSource(url));

  onMount(async () => {
    auth = await api.spotifyAuthStatus().catch(() => null);
    await jobs.refresh();
    refreshAlbums();
  });

  async function refreshAlbums() {
    try {
      const r = await api.albums();
      albums = r.items;
    } catch {
      albums = [];
    }
  }

  async function onPreview() {
    if (!url.trim() || busy) return;
    busy = true;
    preview = null;
    previewError = null;
    lastImportMsg = null;
    try {
      const p = await api.previewIngest(url.trim());
      preview = p;
      // Rellenar overrides con lo resuelto
      ovAlbum = p.tracks[0]?.album || '';
      ovArtist = p.tracks[0]?.artists?.[0] || '';
      ovYear = '';
      ovMode = 'new';
      ovTargetAlbumId = null;
    } catch (e) {
      previewError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  async function onImport() {
    if (!preview || busy) return;
    busy = true;
    const overrides: IngestOverrides = {};
    if (ovMode === 'existing' && ovTargetAlbumId) {
      overrides.target_album_id = ovTargetAlbumId;
    } else if (ovMode === 'new') {
      if (ovAlbum.trim()) overrides.album = ovAlbum.trim();
      if (ovArtist.trim()) overrides.artist = ovArtist.trim();
      if (ovArtist.trim()) overrides.album_artist = ovArtist.trim();
      if (ovYear.trim()) overrides.year = parseInt(ovYear, 10) || undefined;
    }
    try {
      const r = await api.ingest(url.trim(), overrides);
      const sk = r.skipped_track_ids.length;
      lastImportMsg = `${r.created_job_ids.length} ${r.created_job_ids.length === 1 ? 'pista encolada' : 'pistas encoladas'}${sk ? ` (${sk} duplicadas ignoradas)` : ''}.`;
      preview = null;
      url = '';
      await jobs.refresh();
    } catch (e) {
      previewError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  function onPaste(e: ClipboardEvent) {
    const text = e.clipboardData?.getData('text') ?? '';
    const s = detectSource(text);
    if (s !== 'unknown') {
      setTimeout(() => {
        if (url === text || url.trim() === text.trim()) onPreview();
      }, 50);
    }
  }

  async function retry(id: number) { await api.retryJob(id); await jobs.refresh(); }
  async function remove(id: number) { await api.deleteJob(id); await jobs.refresh(); }
  async function retryAllFailed() { await api.retryFailed(); await jobs.refresh(); }
  async function clearFailed() {
    if (!confirm('¿Borrar todos los jobs fallidos?')) return;
    await api.clearJobs('failed'); await jobs.refresh();
  }
  async function clearDone() {
    if (!confirm('¿Borrar todos los completados del historial?')) return;
    await api.clearJobs('done'); await jobs.refresh();
  }

  // ─── Agrupación de jobs ───
  type Group = {
    key: string;
    kind: string;
    name: string;
    cover_url: string | null;
    items: Job[];
    counts: { pending: number; running: number; done: number; failed: number };
  };

  const groups = $derived.by<Group[]>(() => {
    const byUrl = new Map<string, Job[]>();
    for (const j of jobs.items) {
      const arr = byUrl.get(j.source_url) ?? [];
      arr.push(j);
      byUrl.set(j.source_url, arr);
    }
    const out: Group[] = [];
    for (const [key, items] of byUrl) {
      const first = items[0];
      const name =
        first.source_kind === 'album'
          ? first.album || 'Álbum'
          : first.source_kind === 'playlist'
            ? 'Playlist'
            : first.title || 'Pista';
      const counts = {
        pending: items.filter((j) => j.status === 'pending').length,
        running: items.filter((j) => j.status === 'running').length,
        done: items.filter((j) => j.status === 'done').length,
        failed: items.filter((j) => j.status === 'failed').length
      };
      const cover = items.find((j) => j.cover_url)?.cover_url ?? null;
      out.push({ key, kind: first.source_kind, name, cover_url: cover, items, counts });
    }
    out.sort((a, b) => {
      const aT = Math.max(...a.items.map((i) => Date.parse(i.created_at || '0')));
      const bT = Math.max(...b.items.map((i) => Date.parse(i.created_at || '0')));
      return bT - aT;
    });
    return out;
  });

  function kindLabel(k: string): string {
    return ({ track: 'Pista', album: 'Álbum', playlist: 'Playlist' } as Record<string, string>)[k] ?? k;
  }

  function sourceLabel(s: Source): { name: string; color: string; icon: string } {
    return {
      spotify: { name: 'Spotify', color: 'bg-emerald-500/15 text-emerald-300 border-emerald-700/40', icon: '♫' },
      youtube: { name: 'YouTube', color: 'bg-red-500/15 text-red-300 border-red-700/40', icon: '▶' },
      soundcloud: { name: 'SoundCloud', color: 'bg-orange-500/15 text-orange-300 border-orange-700/40', icon: '☁' },
      unknown: { name: 'Desconocido', color: 'bg-neutral-800 text-neutral-400 border-neutral-700', icon: '?' }
    }[s];
  }

  function statusColor(s: Job['status']): string {
    return ({
      pending: 'text-neutral-400',
      running: 'text-sky-400',
      done: 'text-emerald-400',
      failed: 'text-red-400'
    } as Record<string, string>)[s];
  }

  function statusIcon(s: Job['status']): string {
    return ({ pending: '⏱', running: '⟳', done: '✓', failed: '✗' } as Record<string, string>)[s];
  }

  const needsManualMetadata = $derived(
    preview ? preview.source !== 'spotify' || !preview.tracks[0]?.album : false
  );
</script>

<div class="mx-auto max-w-2xl px-4 pt-6">
  <header class="mb-5 flex flex-wrap items-baseline justify-between gap-2">
    <h1 class="text-2xl font-bold">Importar</h1>
    {#if auth}
      <a
        href="/settings"
        class="inline-flex items-center gap-1.5 rounded-full border border-neutral-800 bg-neutral-900 px-3 py-1 text-xs hover:bg-neutral-800"
      >
        {#if auth.cookies_configured}
          <span class="size-2 rounded-full bg-emerald-500"></span>
          <span>Votify · alta calidad</span>
        {:else}
          <span class="size-2 rounded-full bg-amber-500"></span>
          <span>yt-dlp · sin cookies</span>
        {/if}
      </a>
    {/if}
  </header>

  <!-- Source pills -->
  <div class="mb-3 flex flex-wrap items-center gap-1.5 text-xs">
    <span class="text-neutral-500">Fuentes:</span>
    {#each ['spotify', 'youtube', 'soundcloud'] as s (s)}
      {@const info = sourceLabel(s as Source)}
      <span
        class="rounded border px-2 py-0.5 {info.color}"
        class:opacity-100={detectedSource === s}
        class:opacity-40={detectedSource !== s && detectedSource !== 'unknown'}
      >{info.icon} {info.name}</span>
    {/each}
  </div>

  <!-- URL input -->
  <form onsubmit={(e) => { e.preventDefault(); onPreview(); }} class="relative">
    <input
      type="url"
      bind:value={url}
      onpaste={onPaste}
      placeholder="Pega URL de Spotify, YouTube o SoundCloud…"
      autocomplete="off"
      inputmode="url"
      class="w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2.5 pr-24 text-sm placeholder:text-neutral-600 focus:border-emerald-500 focus:outline-none"
    />
    <button
      type="submit"
      disabled={busy || !url.trim() || detectedSource === 'unknown'}
      class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded bg-neutral-800 px-3 py-1.5 text-xs font-medium hover:bg-neutral-700 disabled:opacity-40"
    >
      {busy && !preview ? '…' : 'Examinar'}
    </button>
  </form>

  {#if detectedSource === 'unknown' && url.trim().length > 5}
    <p class="mt-2 text-xs text-amber-400">
      URL no reconocida — soporta Spotify, YouTube y SoundCloud.
    </p>
  {/if}

  {#if previewError}
    <div class="mt-3 rounded-md border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
      ⚠️ {previewError}
    </div>
  {/if}

  {#if lastImportMsg}
    <div class="mt-3 rounded-md border border-emerald-900/50 bg-emerald-950/30 p-3 text-sm text-emerald-300">
      ✓ {lastImportMsg}
    </div>
  {/if}

  {#if busy && !preview && !previewError}
    <section class="mt-4 overflow-hidden rounded-lg border border-neutral-800 bg-neutral-900">
      <div class="flex items-start gap-3 p-4">
        <div class="size-20 flex-none animate-pulse rounded bg-neutral-800"></div>
        <div class="min-w-0 flex-1 space-y-2 pt-1">
          <div class="h-3 w-24 animate-pulse rounded bg-neutral-800"></div>
          <div class="h-5 w-3/4 animate-pulse rounded bg-neutral-800"></div>
          <div class="h-3 w-1/2 animate-pulse rounded bg-neutral-800"></div>
        </div>
      </div>
      <div class="flex items-center gap-2 border-t border-neutral-800 bg-neutral-950 px-4 py-2.5 text-xs text-sky-400">
        <span class="size-1.5 animate-pulse rounded-full bg-sky-400"></span>
        Examinando URL…
      </div>
    </section>
  {/if}

  {#if preview}
    {@const srcInfo = sourceLabel(preview.source)}
    <section class="mt-4 overflow-hidden rounded-lg border border-emerald-900/40 bg-neutral-900">
      <div class="flex items-start gap-3 p-4">
        {#if preview.tracks[0]?.cover_url}
          <img src={preview.tracks[0].cover_url} alt="" class="size-20 flex-none rounded object-cover" />
        {:else}
          <div class="grid size-20 flex-none place-items-center rounded bg-neutral-800 text-2xl">🎵</div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex items-center gap-2">
            <span class="rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider {srcInfo.color}">
              {srcInfo.icon} {srcInfo.name}
            </span>
            <span class="text-xs text-neutral-500">{kindLabel(preview.kind)}</span>
          </div>
          <h2 class="text-lg font-semibold leading-tight">{preview.name}</h2>
          <p class="mt-1 text-xs text-neutral-400">
            {preview.total_tracks} {preview.total_tracks === 1 ? 'pista' : 'pistas'}
            {#if preview.tracks[0]?.artists.length}
              · {preview.tracks[0].artists.join(', ')}
            {/if}
          </p>
        </div>
      </div>

      <!-- Metadata override -->
      {#if needsManualMetadata}
        <div class="border-t border-neutral-800 bg-neutral-950 p-4">
          <p class="mb-3 text-xs uppercase tracking-wider text-neutral-500">
            Organizar como…
          </p>
          <div class="mb-3 flex gap-2 text-xs">
            <label class="flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded border px-3 py-1.5"
              class:border-emerald-500={ovMode === 'new'}
              class:border-neutral-800={ovMode !== 'new'}
              class:bg-emerald-500={ovMode === 'new'}
              class:text-neutral-950={ovMode === 'new'}
              class:font-semibold={ovMode === 'new'}>
              <input type="radio" bind:group={ovMode} value="new" class="sr-only" />
              Álbum nuevo
            </label>
            <label class="flex flex-1 cursor-pointer items-center justify-center gap-1.5 rounded border px-3 py-1.5"
              class:border-emerald-500={ovMode === 'existing'}
              class:border-neutral-800={ovMode !== 'existing'}
              class:bg-emerald-500={ovMode === 'existing'}
              class:text-neutral-950={ovMode === 'existing'}
              class:font-semibold={ovMode === 'existing'}>
              <input type="radio" bind:group={ovMode} value="existing" class="sr-only" />
              Añadir a existente
            </label>
          </div>

          {#if ovMode === 'new'}
            <div class="space-y-2 text-sm">
              <label class="block">
                <span class="text-xs text-neutral-400">Álbum</span>
                <input
                  type="text"
                  bind:value={ovAlbum}
                  placeholder="Nombre del álbum (vacío → Singles)"
                  class="mt-1 w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-neutral-400">Artista</span>
                <input
                  type="text"
                  bind:value={ovArtist}
                  placeholder="Nombre del artista"
                  class="mt-1 w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-neutral-400">Año <span class="text-neutral-600">(opcional)</span></span>
                <input
                  type="number"
                  bind:value={ovYear}
                  placeholder="2024"
                  min="1900"
                  max="2100"
                  class="mt-1 w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
                />
              </label>
            </div>
          {:else}
            <div class="text-sm">
              {#if albums.length === 0}
                <p class="rounded border border-neutral-800 bg-neutral-900 p-3 text-xs text-neutral-500">
                  No tienes álbumes todavía. Crea uno nuevo primero.
                </p>
              {:else}
                <label class="block">
                  <span class="text-xs text-neutral-400">Álbum existente</span>
                  <select
                    bind:value={ovTargetAlbumId}
                    class="mt-1 w-full rounded border border-neutral-800 bg-neutral-900 px-2 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    <option value={null}>— seleccionar —</option>
                    {#each albums as a}
                      <option value={a.id}>
                        {a.title} · {a.artist_name} ({a.track_count})
                      </option>
                    {/each}
                  </select>
                </label>
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      <div class="border-t border-neutral-800 bg-neutral-900 p-3">
        <button
          onclick={onImport}
          disabled={busy || (ovMode === 'existing' && !ovTargetAlbumId)}
          class="w-full rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          {busy ? 'Encolando…' : `Importar ${preview.total_tracks} ${preview.total_tracks === 1 ? 'pista' : 'pistas'}`}
        </button>
      </div>

      {#if preview.tracks.length > 1}
        <details class="border-t border-neutral-800">
          <summary class="cursor-pointer px-4 py-2 text-xs text-neutral-400 hover:bg-neutral-950">
            Ver tracklist ({preview.tracks.length})
          </summary>
          <ul class="divide-y divide-neutral-800 text-sm">
            {#each preview.tracks.slice(0, 50) as t}
              <li class="flex items-center justify-between px-4 py-1.5">
                <span class="truncate">
                  <span class="mr-2 text-xs text-neutral-500">{String(t.track_number).padStart(2, '0')}</span>
                  {t.title}
                </span>
                <span class="font-mono text-xs text-neutral-500">{formatDuration(t.duration_ms)}</span>
              </li>
            {/each}
            {#if preview.tracks.length > 50}
              <li class="px-4 py-2 text-center text-xs text-neutral-500">
                + {preview.tracks.length - 50} más…
              </li>
            {/if}
          </ul>
        </details>
      {/if}
    </section>
  {/if}

  <!-- Cola -->
  <section class="mt-10">
    <header class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-neutral-500">
        Cola de descarga
      </h2>
      <div class="flex flex-wrap gap-1.5 text-xs">
        {#if jobs.stats.failed > 0}
          <button
            onclick={retryAllFailed}
            class="rounded border border-neutral-800 px-2 py-1 hover:bg-neutral-800"
          >↻ reintentar {jobs.stats.failed} fallidos</button>
          <button
            onclick={clearFailed}
            class="rounded border border-neutral-800 px-2 py-1 hover:bg-neutral-800"
          >× borrar fallidos</button>
        {/if}
        {#if jobs.stats.done > 0}
          <button
            onclick={clearDone}
            class="rounded border border-neutral-800 px-2 py-1 text-neutral-500 hover:bg-neutral-800"
          >limpiar historial</button>
        {/if}
      </div>
    </header>

    <div class="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-xs">
      <span class="text-neutral-400">Total: <b class="text-neutral-200">{jobs.stats.total}</b></span>
      {#if jobs.stats.pending > 0}<span class="text-neutral-400">⏱ {jobs.stats.pending}</span>{/if}
      {#if jobs.stats.running > 0}<span class="text-sky-400">⟳ {jobs.stats.running}</span>{/if}
      {#if jobs.stats.done > 0}<span class="text-emerald-400">✓ {jobs.stats.done}</span>{/if}
      {#if jobs.stats.failed > 0}<span class="text-red-400">✗ {jobs.stats.failed}</span>{/if}
      {#if jobs.active > 0}
        <span class="ml-auto inline-flex items-center gap-1 text-sky-400">
          <span class="size-1.5 animate-pulse rounded-full bg-sky-400"></span>
          descargando…
        </span>
      {/if}
    </div>

    {#if groups.length === 0}
      <div class="rounded-md border border-dashed border-neutral-800 p-8 text-center">
        <p class="text-sm text-neutral-400">Sin importaciones todavía.</p>
        <p class="mt-2 text-xs text-neutral-600">
          Prueba pegando una URL: <br />
          spotify.com · youtube.com · soundcloud.com
        </p>
      </div>
    {:else}
      <ul class="space-y-2">
        {#each groups as g (g.key)}
          {@const total = g.items.length}
          {@const isOpen = expanded[g.key] ?? false}
          <li class="overflow-hidden rounded-md border border-neutral-800 bg-neutral-900">
            <button
              type="button"
              onclick={() => (expanded[g.key] = !isOpen)}
              class="flex w-full items-center gap-3 p-3 text-left hover:bg-neutral-800/50"
            >
              {#if g.cover_url}
                <img src={g.cover_url} alt="" class="size-12 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-12 flex-none place-items-center rounded bg-neutral-800 text-lg">
                  {g.kind === 'album' ? '◉' : g.kind === 'playlist' ? '☰' : '♪'}
                </div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="flex items-baseline gap-2">
                  <span class="text-xs uppercase text-neutral-500">{kindLabel(g.kind)}</span>
                  <span class="truncate text-sm font-medium">{g.name}</span>
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <span class="block h-1 w-20 overflow-hidden rounded-full bg-neutral-800">
                    <span
                      class="block h-full bg-emerald-500"
                      style:width="{total > 0 ? Math.round((g.counts.done / total) * 100) : 0}%"
                    ></span>
                  </span>
                  <span class="text-neutral-500">{g.counts.done}/{total}</span>
                  {#if g.counts.running > 0}
                    <span class="text-sky-400">⟳ {g.counts.running}</span>
                  {/if}
                  {#if g.counts.failed > 0}
                    <span class="text-red-400">✗ {g.counts.failed}</span>
                  {/if}
                </div>
              </div>
              <span class="text-neutral-500">{isOpen ? '▾' : '▸'}</span>
            </button>

            {#if isOpen}
              <ul class="divide-y divide-neutral-800 border-t border-neutral-800 bg-neutral-950">
                {#each g.items as job (job.id)}
                  <li class="px-3 py-2">
                    <div class="flex items-center gap-3">
                      <span
                        class="w-5 flex-none text-center font-mono text-xs {statusColor(job.status)}"
                        class:animate-spin={job.status === 'running'}
                      >{statusIcon(job.status)}</span>
                      <div class="min-w-0 flex-1">
                        <div class="truncate text-sm">{job.title}</div>
                        <div class="truncate text-xs text-neutral-500">
                          {job.artist}
                          {#if job.album} · {job.album}{/if}
                          {#if job.backend_used} · {job.backend_used}{/if}
                          {#if job.duration_ms} · {formatDuration(job.duration_ms)}{/if}
                        </div>
                        {#if job.error}
                          <div class="mt-0.5 truncate text-xs text-red-400/80" title={job.error}>{job.error}</div>
                        {/if}
                      </div>
                      <div class="flex flex-none gap-1">
                        {#if job.status === 'failed'}
                          <button
                            onclick={() => retry(job.id)}
                            class="rounded border border-neutral-800 px-2 py-1 text-xs hover:bg-neutral-800"
                            title="Reintentar"
                          >↻</button>
                        {/if}
                        {#if job.status !== 'running'}
                          <button
                            onclick={() => remove(job.id)}
                            class="rounded border border-neutral-800 px-2 py-1 text-xs text-neutral-500 hover:bg-neutral-800 hover:text-red-400"
                            title="Eliminar"
                          >×</button>
                        {/if}
                      </div>
                    </div>
                    {#if job.status === 'running'}
                      <div class="mt-1.5 ml-8 flex items-center gap-2 text-[10px] text-sky-300">
                        <span class="relative block h-1 flex-1 overflow-hidden rounded-full bg-neutral-800">
                          <span
                            class="block h-full bg-sky-400 transition-all duration-500"
                            style:width="{Math.max(2, job.progress)}%"
                          ></span>
                          <!-- Stripe indeterminado encima cuando estamos atascados en 95% (convirtiendo) -->
                          {#if job.progress >= 90 && job.progress < 100}
                            <span class="absolute inset-0 animate-pulse bg-gradient-to-r from-transparent via-sky-300/20 to-transparent"></span>
                          {/if}
                        </span>
                        <span class="w-9 text-right font-mono">{job.progress}%</span>
                        {#if job.stage}
                          <span class="text-neutral-500">· {job.stage}</span>
                        {/if}
                      </div>
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>
