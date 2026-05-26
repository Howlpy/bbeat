<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    formatDuration,
    type Album,
    type IngestPreview,
    type IngestOverrides,
    type Job,
    type Source
  } from '$lib/api';
  import { jobs } from '$lib/jobs.svelte';
  import { Check, ChevronDown, ChevronRight, Clock, Disc3, List, Loader2, Music2, RefreshCw, Trash2, X } from 'lucide-svelte';
  import LocalUpload from '$lib/components/LocalUpload.svelte';

  let tab = $state<'url' | 'file'>('url');

  let url = $state('');
  let busy = $state(false);
  let preview = $state<IngestPreview | null>(null);
  let previewError = $state<string | null>(null);
  let lastImportMsg = $state<string | null>(null);
  let albums = $state<Album[]>([]);
  let expanded = $state<Record<string, boolean>>({});

  // Selección de pistas del preview (todas marcadas por defecto)
  let selected = $state<Record<string, boolean>>({});
  const selectedCount = $derived(
    preview ? preview.tracks.filter((t) => selected[t.spotify_id]).length : 0
  );
  const allSelected = $derived(
    preview ? preview.tracks.length > 0 && preview.tracks.every((t) => selected[t.spotify_id]) : false
  );

  function toggleAll(v: boolean) {
    if (!preview) return;
    for (const t of preview.tracks) selected[t.spotify_id] = v;
    selected = { ...selected };
  }

  // Destino de la importación.
  //  'auto'     → sin override; el backend decide por tipo: canción→suelta,
  //               álbum→su álbum, playlist→colección.
  //  'new'      → crear álbum/playlist nuevo con nombre.
  //  'existing' → añadir a uno tuyo.
  let ovMode = $state<'auto' | 'new' | 'existing'>('auto');
  let ovAlbum = $state('');
  let ovArtist = $state('');
  let ovYear = $state<string>('');
  let ovTargetAlbumId = $state<number | null>(null);

  // Etiqueta de la opción 'auto' según el tipo de lo que se importa.
  const autoLabel = $derived(
    preview?.kind === 'album'
      ? 'Su álbum'
      : preview?.kind === 'playlist'
        ? 'Como playlist'
        : 'Canción suelta'
  );

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
    await jobs.refresh();
    refreshAlbums();
  });

  async function refreshAlbums() {
    try {
      // Destino de importación: solo álbumes/playlists que puedes mutar.
      const r = await api.albums('mine');
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
      // Todas las pistas marcadas por defecto
      selected = Object.fromEntries(p.tracks.map((t) => [t.spotify_id, true]));
      // Rellenar sugerencias para la opción 'nuevo'; destino por defecto = auto.
      ovAlbum = p.kind === 'playlist' ? p.name : p.tracks[0]?.album || '';
      ovArtist = p.tracks[0]?.artists?.[0] || '';
      ovYear = '';
      ovMode = 'auto';
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
    // 'auto' → sin overrides; el backend agrupa según el tipo (suelta/álbum/colección).
    try {
      const onlyIds =
        preview.tracks.length > 1
          ? preview.tracks.filter((t) => selected[t.spotify_id]).map((t) => t.spotify_id)
          : undefined;
      const r = await api.ingest(url.trim(), overrides, onlyIds);
      const created = r.created_job_ids.length;
      const dedupedCount = r.deduped.length;
      const addedToAlbum = r.deduped.filter((d) => d.added_to_album_id !== null).length;
      const sk = r.skipped_track_ids.length;
      const parts: string[] = [];
      if (created > 0) parts.push(`${created} ${created === 1 ? 'nueva descarga' : 'nuevas descargas'}`);
      if (dedupedCount > 0) {
        if (addedToAlbum > 0) {
          parts.push(`${addedToAlbum} ya tenías${addedToAlbum > 1 ? 'mos' : 'mos'} → añadid${addedToAlbum === 1 ? 'a' : 'as'} a tu álbum`);
        } else {
          parts.push(`${dedupedCount} ya en biblioteca`);
        }
      }
      if (sk > 0) parts.push(`${sk} ignoradas (job duplicado)`);
      lastImportMsg = parts.length ? parts.join(' · ') : 'Sin cambios.';
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

  function sourceLabel(s: Source): { name: string; color: string } {
    return {
      spotify: { name: 'Spotify', color: 'bg-cyan-500/15 text-cyan-300 border-cyan-700/40' },
      youtube: { name: 'YouTube', color: 'bg-red-500/15 text-red-300 border-red-700/40' },
      soundcloud: { name: 'SoundCloud', color: 'bg-orange-500/15 text-orange-300 border-orange-700/40' },
      unknown: { name: 'Desconocido', color: 'bg-slate-800 text-slate-400 border-slate-700' }
    }[s];
  }

  function statusColor(s: Job['status']): string {
    return ({
      pending: 'text-slate-400',
      running: 'text-sky-400',
      done: 'text-cyan-400',
      failed: 'text-red-400'
    } as Record<string, string>)[s];
  }

  // Componente de icono según estado
  const STATUS_ICON = {
    pending: Clock,
    running: Loader2,
    done: Check,
    failed: X
  } as const;

</script>

<div class="mx-auto max-w-2xl px-4 pt-6">
  <header class="mb-5 flex flex-wrap items-baseline justify-between gap-2">
    <h1 class="text-2xl font-bold">Importar</h1>
  </header>

  <!-- Tabs -->
  <div class="mb-4 flex gap-1 rounded-md border border-slate-800 bg-slate-900 p-1 text-sm">
    <button
      onclick={() => (tab = 'url')}
      class="flex-1 rounded px-3 py-1.5"
      class:bg-slate-800={tab === 'url'}
    >URL (Spotify · YouTube · SoundCloud)</button>
    <button
      onclick={() => (tab = 'file')}
      class="flex-1 rounded px-3 py-1.5"
      class:bg-slate-800={tab === 'file'}
    >Ficheros locales</button>
  </div>

  {#if tab === 'url'}
  <!-- Source pills -->
  <div class="mb-3 flex flex-wrap items-center gap-1.5 text-xs">
    <span class="text-slate-500">Fuentes:</span>
    {#each ['spotify', 'youtube', 'soundcloud'] as s (s)}
      {@const info = sourceLabel(s as Source)}
      <span
        class="rounded border px-2 py-0.5 {info.color}"
        class:opacity-100={detectedSource === s}
        class:opacity-40={detectedSource !== s && detectedSource !== 'unknown'}
      >{info.name}</span>
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
      class="w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2.5 pr-24 text-sm placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
    />
    <button
      type="submit"
      disabled={busy || !url.trim() || detectedSource === 'unknown'}
      class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded bg-slate-800 px-3 py-1.5 text-xs font-medium hover:bg-slate-700 disabled:opacity-40"
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
      {previewError}
    </div>
  {/if}

  {#if lastImportMsg}
    <div class="mt-3 rounded-md border border-cyan-900/50 bg-cyan-950/30 p-3 text-sm text-cyan-300">
      {lastImportMsg}
    </div>
  {/if}

  {#if busy && !preview && !previewError}
    <section class="mt-4 overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
      <div class="flex items-start gap-3 p-4">
        <div class="size-20 flex-none animate-pulse rounded bg-slate-800"></div>
        <div class="min-w-0 flex-1 space-y-2 pt-1">
          <div class="h-3 w-24 animate-pulse rounded bg-slate-800"></div>
          <div class="h-5 w-3/4 animate-pulse rounded bg-slate-800"></div>
          <div class="h-3 w-1/2 animate-pulse rounded bg-slate-800"></div>
        </div>
      </div>
      <div class="flex items-center gap-2 border-t border-slate-800 bg-slate-950 px-4 py-2.5 text-xs text-sky-400">
        <span class="size-1.5 animate-pulse rounded-full bg-sky-400"></span>
        Examinando URL…
      </div>
    </section>
  {/if}

  {#if preview}
    {@const srcInfo = sourceLabel(preview.source)}
    <section class="mt-4 overflow-hidden rounded-lg border border-cyan-900/40 bg-slate-900">
      <div class="flex items-start gap-3 p-4">
        {#if preview.tracks[0]?.cover_url}
          <img src={preview.tracks[0].cover_url} alt="" class="size-20 flex-none rounded object-cover" />
        {:else}
          <div class="grid size-20 flex-none place-items-center rounded bg-slate-800 text-slate-600">
            <Music2 size={28} />
          </div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex items-center gap-2">
            <span class="rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wider {srcInfo.color}">
              {srcInfo.name}
            </span>
            <span class="text-xs text-slate-500">{kindLabel(preview.kind)}</span>
          </div>
          <h2 class="text-lg font-semibold leading-tight">{preview.name}</h2>
          <p class="mt-1 text-xs text-slate-400">
            {preview.total_tracks} {preview.total_tracks === 1 ? 'pista' : 'pistas'}
            {#if preview.tracks[0]?.artists.length}
              · {preview.tracks[0].artists.join(', ')}
            {/if}
          </p>
        </div>
      </div>

      <!-- Destino de la importación -->
      <div class="border-t border-slate-800 bg-slate-950 p-4">
          <p class="mb-3 text-xs uppercase tracking-wider text-slate-500">
            ¿Dónde van estas canciones?
          </p>
          <div class="mb-3 grid grid-cols-3 gap-2 text-xs">
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded border px-2 py-1.5 text-center"
              class:border-cyan-500={ovMode === 'auto'}
              class:border-slate-800={ovMode !== 'auto'}
              class:bg-cyan-500={ovMode === 'auto'}
              class:text-slate-950={ovMode === 'auto'}
              class:font-semibold={ovMode === 'auto'}>
              <input type="radio" bind:group={ovMode} value="auto" class="sr-only" />
              {autoLabel}
            </label>
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded border px-2 py-1.5 text-center"
              class:border-cyan-500={ovMode === 'new'}
              class:border-slate-800={ovMode !== 'new'}
              class:bg-cyan-500={ovMode === 'new'}
              class:text-slate-950={ovMode === 'new'}
              class:font-semibold={ovMode === 'new'}>
              <input type="radio" bind:group={ovMode} value="new" class="sr-only" />
              Álbum/playlist nuevo
            </label>
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded border px-2 py-1.5 text-center"
              class:border-cyan-500={ovMode === 'existing'}
              class:border-slate-800={ovMode !== 'existing'}
              class:bg-cyan-500={ovMode === 'existing'}
              class:text-slate-950={ovMode === 'existing'}
              class:font-semibold={ovMode === 'existing'}>
              <input type="radio" bind:group={ovMode} value="existing" class="sr-only" />
              Añadir a uno tuyo
            </label>
          </div>

          {#if ovMode === 'auto'}
            <p class="rounded border border-slate-800 bg-slate-900 p-3 text-xs text-slate-400">
              {#if preview.kind === 'album'}
                Se guardan como su álbum original.
              {:else if preview.kind === 'playlist'}
                Se agrupan en una playlist “{preview.name}” (varios artistas).
              {:else}
                {selectedCount === 1 ? 'La canción entra' : 'Las canciones entran'} sueltas, sin álbum. Podrás añadirlas a una playlist cuando quieras.
              {/if}
            </p>
          {:else if ovMode === 'new'}
            <div class="space-y-2 text-sm">
              <label class="block">
                <span class="text-xs text-slate-400">Álbum</span>
                <input
                  type="text"
                  bind:value={ovAlbum}
                  placeholder="Nombre del álbum (vacío → Singles)"
                  class="mt-1 w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-slate-400">Artista</span>
                <input
                  type="text"
                  bind:value={ovArtist}
                  placeholder="Nombre del artista"
                  class="mt-1 w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-slate-400">Año <span class="text-slate-600">(opcional)</span></span>
                <input
                  type="number"
                  bind:value={ovYear}
                  placeholder="2024"
                  min="1900"
                  max="2100"
                  class="mt-1 w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
                />
              </label>
            </div>
          {:else}
            <div class="text-sm">
              {#if albums.length === 0}
                <p class="rounded border border-slate-800 bg-slate-900 p-3 text-xs text-slate-500">
                  No tienes álbumes todavía. Crea uno nuevo primero.
                </p>
              {:else}
                <label class="block">
                  <span class="text-xs text-slate-400">Álbum existente</span>
                  <select
                    bind:value={ovTargetAlbumId}
                    class="mt-1 w-full rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
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

      <div class="border-t border-slate-800 bg-slate-900 p-3">
        <button
          onclick={onImport}
          disabled={busy || selectedCount === 0 || (ovMode === 'existing' && !ovTargetAlbumId)}
          class="w-full rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
        >
          {busy ? 'Encolando…' : `Importar ${selectedCount} ${selectedCount === 1 ? 'pista' : 'pistas'}`}
        </button>
      </div>

      {#if preview.tracks.length > 1}
        <div class="border-t border-slate-800">
          <div class="flex items-center justify-between px-4 py-2 text-xs">
            <span class="text-slate-400">{selectedCount} de {preview.tracks.length} seleccionadas</span>
            <button
              type="button"
              onclick={() => toggleAll(!allSelected)}
              class="font-medium text-cyan-400 hover:underline"
            >{allSelected ? 'Quitar todas' : 'Marcar todas'}</button>
          </div>
          <ul class="max-h-72 divide-y divide-slate-800 overflow-y-auto text-sm">
            {#each preview.tracks as t (t.spotify_id)}
              <li>
                <label class="flex cursor-pointer items-center gap-3 px-4 py-1.5 hover:bg-slate-950">
                  <input
                    type="checkbox"
                    bind:checked={selected[t.spotify_id]}
                    class="size-4 flex-none accent-cyan-500"
                  />
                  <span class="min-w-0 flex-1 truncate" class:text-slate-600={!selected[t.spotify_id]}>
                    {t.title}
                  </span>
                  <span class="flex-none font-mono text-xs text-slate-500">{formatDuration(t.duration_ms)}</span>
                </label>
              </li>
            {/each}
          </ul>
        </div>
      {/if}
    </section>
  {/if}

  {:else}
    <LocalUpload albums={albums} onuploaded={() => refreshAlbums()} />
  {/if}

  <!-- Cola -->
  <section class="mt-10">
    <header class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-500">
        Cola de descarga
      </h2>
      <div class="flex flex-wrap gap-1.5 text-xs">
        {#if jobs.stats.failed > 0}
          <button
            onclick={retryAllFailed}
            class="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 transition hover:bg-slate-800"
          ><RefreshCw size={12} /> reintentar {jobs.stats.failed} fallidos</button>
          <button
            onclick={clearFailed}
            class="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 transition hover:bg-slate-800"
          ><Trash2 size={12} /> borrar fallidos</button>
        {/if}
        {#if jobs.stats.done > 0}
          <button
            onclick={clearDone}
            class="rounded border border-slate-800 px-2 py-1 text-slate-500 hover:bg-slate-800"
          >limpiar historial</button>
        {/if}
      </div>
    </header>

    <div class="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-xs">
      <span class="text-slate-400">Total: <b class="text-slate-200">{jobs.stats.total}</b></span>
      {#if jobs.stats.pending > 0}
        <span class="inline-flex items-center gap-1 text-slate-400"><Clock size={11} /> {jobs.stats.pending}</span>
      {/if}
      {#if jobs.stats.running > 0}
        <span class="inline-flex items-center gap-1 text-sky-400"><Loader2 size={11} class="animate-spin" /> {jobs.stats.running}</span>
      {/if}
      {#if jobs.stats.done > 0}
        <span class="inline-flex items-center gap-1 text-cyan-400"><Check size={11} /> {jobs.stats.done}</span>
      {/if}
      {#if jobs.stats.failed > 0}
        <span class="inline-flex items-center gap-1 text-red-400"><X size={11} /> {jobs.stats.failed}</span>
      {/if}
      {#if jobs.active > 0}
        <span class="ml-auto inline-flex items-center gap-1 text-sky-400">
          <span class="size-1.5 animate-pulse rounded-full bg-sky-400"></span>
          descargando…
        </span>
      {/if}
    </div>

    {#if groups.length === 0}
      <div class="rounded-md border border-dashed border-slate-800 p-8 text-center">
        <p class="text-sm text-slate-400">Sin importaciones todavía.</p>
        <p class="mt-2 text-xs text-slate-600">
          Prueba pegando una URL: <br />
          spotify.com · youtube.com · soundcloud.com
        </p>
      </div>
    {:else}
      <ul class="space-y-2">
        {#each groups as g (g.key)}
          {@const total = g.items.length}
          {@const isOpen = expanded[g.key] ?? false}
          <li class="overflow-hidden rounded-md border border-slate-800 bg-slate-900">
            <button
              type="button"
              onclick={() => (expanded[g.key] = !isOpen)}
              class="flex w-full items-center gap-3 p-3 text-left hover:bg-slate-800/50"
            >
              {#if g.cover_url}
                <img src={g.cover_url} alt="" class="size-12 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-12 flex-none place-items-center rounded bg-slate-800 text-slate-500">
                  {#if g.kind === 'album'}
                    <Disc3 size={20} />
                  {:else if g.kind === 'playlist'}
                    <List size={20} />
                  {:else}
                    <Music2 size={20} />
                  {/if}
                </div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="flex items-baseline gap-2">
                  <span class="text-xs uppercase text-slate-500">{kindLabel(g.kind)}</span>
                  <span class="truncate text-sm font-medium">{g.name}</span>
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <span class="block h-1 w-20 overflow-hidden rounded-full bg-slate-800">
                    <span
                      class="block h-full bg-cyan-400"
                      style:width="{total > 0 ? Math.round((g.counts.done / total) * 100) : 0}%"
                    ></span>
                  </span>
                  <span class="text-slate-500">{g.counts.done}/{total}</span>
                  {#if g.counts.running > 0}
                    <span class="inline-flex items-center gap-0.5 text-sky-400">
                      <Loader2 size={10} class="animate-spin" /> {g.counts.running}
                    </span>
                  {/if}
                  {#if g.counts.failed > 0}
                    <span class="inline-flex items-center gap-0.5 text-red-400">
                      <X size={10} /> {g.counts.failed}
                    </span>
                  {/if}
                </div>
              </div>
              <span class="text-slate-500">
                {#if isOpen}<ChevronDown size={16} />{:else}<ChevronRight size={16} />{/if}
              </span>
            </button>

            {#if isOpen}
              <ul class="divide-y divide-slate-800 border-t border-slate-800 bg-slate-950">
                {#each g.items as job (job.id)}
                  {@const StatusIcon = STATUS_ICON[job.status]}
                  <li class="px-3 py-2">
                    <div class="flex items-center gap-3">
                      <span class="flex w-5 flex-none items-center justify-center {statusColor(job.status)}">
                        <StatusIcon size={14} class={job.status === 'running' ? 'animate-spin' : ''} />
                      </span>
                      <div class="min-w-0 flex-1">
                        <div class="truncate text-sm">{job.title}</div>
                        <div class="truncate text-xs text-slate-500">
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
                            class="grid size-7 place-items-center rounded border border-slate-800 transition hover:bg-slate-800"
                            title="Reintentar"
                          ><RefreshCw size={12} /></button>
                        {/if}
                        {#if job.status !== 'running'}
                          <button
                            onclick={() => remove(job.id)}
                            class="grid size-7 place-items-center rounded border border-slate-800 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
                            title="Eliminar"
                          ><X size={12} /></button>
                        {/if}
                      </div>
                    </div>
                    {#if job.status === 'running'}
                      <div class="mt-1.5 ml-8 flex items-center gap-2 text-[10px] text-sky-300">
                        <span class="relative block h-1 flex-1 overflow-hidden rounded-full bg-slate-800">
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
                          <span class="text-slate-500">· {job.stage}</span>
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
