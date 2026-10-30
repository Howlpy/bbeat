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
      ovArtist = p.kind === 'playlist' ? 'Various Artists' : p.tracks[0]?.artists?.[0] || '';
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
      if (ovArtist.trim()) {
        // En una playlist multiartista este campo nombra la colección, pero no
        // debe sustituir al intérprete real de cada canción.
        if (preview.kind !== 'playlist') overrides.artist = ovArtist.trim();
        overrides.album_artist = ovArtist.trim();
      }
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
      spotify: { name: 'Spotify', color: 'bg-accent/15 text-accent border-accent/40' },
      youtube: { name: 'YouTube', color: 'bg-danger/15 text-danger border-danger/40' },
      soundcloud: { name: 'SoundCloud', color: 'bg-warning/15 text-warning border-warning/40' },
      unknown: { name: 'Desconocido', color: 'bg-surface-2 text-fg-muted border-line-strong' }
    }[s];
  }

  function statusColor(s: Job['status']): string {
    return ({
      pending: 'text-fg-muted',
      running: 'text-accent',
      done: 'text-accent',
      failed: 'text-danger'
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

<div class="page-narrow">
  <header class="mb-6 flex flex-wrap items-baseline justify-between gap-2">
    <h1 class="page-title">Importar</h1>
  </header>

  <!-- Tabs -->
  <div class="mb-6 flex gap-1 rounded-lg bg-surface p-1 text-sm">
    <button
      onclick={() => (tab = 'url')}
      class="min-h-10 flex-1 rounded-md px-3 text-fg-muted"
      class:bg-surface-3={tab === 'url'}
      class:text-fg={tab === 'url'}
    >URL (Spotify · YouTube · SoundCloud)</button>
    <button
      onclick={() => (tab = 'file')}
      class="min-h-10 flex-1 rounded-md px-3 text-fg-muted"
      class:bg-surface-3={tab === 'file'}
      class:text-fg={tab === 'file'}
    >Ficheros locales</button>
  </div>

  {#if tab === 'url'}
  <!-- Source pills -->
  <div class="mb-3 flex flex-wrap items-center gap-1.5 text-xs">
    <span class="text-fg-subtle">Fuentes:</span>
    {#each ['spotify', 'youtube', 'soundcloud'] as s (s)}
      {@const info = sourceLabel(s as Source)}
      <span
        class="rounded-lg border px-2 py-0.5 {info.color}"
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
      class="w-full rounded-lg border border-line bg-surface px-3 pr-28 text-sm placeholder:text-fg-subtle focus:border-accent focus:outline-none"
    />
    <button
      type="submit"
      disabled={busy || !url.trim() || detectedSource === 'unknown'}
      class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg bg-surface-3 px-3 py-2 text-sm font-medium hover:bg-line-strong disabled:opacity-40"
    >
      {busy && !preview ? '…' : 'Examinar'}
    </button>
  </form>

  {#if detectedSource === 'unknown' && url.trim().length > 5}
    <p class="mt-2 text-xs text-warning">
      URL no reconocida — soporta Spotify, YouTube y SoundCloud.
    </p>
  {/if}

  {#if previewError}
    <div class="mt-3 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
      {previewError}
    </div>
  {/if}

  {#if lastImportMsg}
    <div class="mt-3 rounded-lg border border-accent/40 bg-accent-soft p-3 text-sm text-accent">
      {lastImportMsg}
    </div>
  {/if}

  {#if busy && !preview && !previewError}
    <section class="mt-4 overflow-hidden rounded-lg border border-line bg-surface">
      <div class="flex items-start gap-3 p-4">
        <div class="size-20 flex-none animate-pulse rounded-lg bg-surface-2"></div>
        <div class="min-w-0 flex-1 space-y-2 pt-1">
          <div class="h-3 w-24 animate-pulse rounded-lg bg-surface-2"></div>
          <div class="h-5 w-3/4 animate-pulse rounded-lg bg-surface-2"></div>
          <div class="h-3 w-1/2 animate-pulse rounded-lg bg-surface-2"></div>
        </div>
      </div>
      <div class="flex items-center gap-2 border-t border-line bg-bg px-4 py-2.5 text-xs text-accent">
        <span class="size-1.5 animate-pulse rounded-full bg-accent"></span>
        Examinando URL…
      </div>
    </section>
  {/if}

  {#if preview}
    {@const srcInfo = sourceLabel(preview.source)}
    <section class="mt-4 overflow-hidden rounded-lg border border-accent/40 bg-surface">
      <div class="flex items-start gap-3 p-4">
        {#if preview.tracks[0]?.cover_url}
          <img loading="lazy" decoding="async" src={preview.tracks[0].cover_url} alt="" class="size-20 flex-none rounded-lg object-cover" />
        {:else}
          <div class="grid size-20 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
            <Music2 size={28} />
          </div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex items-center gap-2">
            <span class="rounded-lg border px-1.5 py-0.5 text-xs uppercase tracking-wider {srcInfo.color}">
              {srcInfo.name}
            </span>
            <span class="text-xs text-fg-subtle">{kindLabel(preview.kind)}</span>
          </div>
          <h2 class="text-lg font-semibold leading-tight">{preview.name}</h2>
          <p class="mt-1 text-xs text-fg-muted">
            {preview.total_tracks} {preview.total_tracks === 1 ? 'pista' : 'pistas'}
            {#if preview.tracks[0]?.artists.length}
              · {preview.tracks[0].artists.join(', ')}
            {/if}
          </p>
        </div>
      </div>

      <!-- Destino de la importación -->
      <div class="border-t border-line bg-bg p-4">
          <p class="mb-3 text-xs uppercase tracking-wider text-fg-subtle">
            ¿Dónde van estas canciones?
          </p>
          <div class="mb-3 grid grid-cols-3 gap-2 text-xs">
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-center"
              class:border-accent={ovMode === 'auto'}
              class:border-line={ovMode !== 'auto'}
              class:bg-accent={ovMode === 'auto'}
              class:text-accent-fg={ovMode === 'auto'}
              class:font-semibold={ovMode === 'auto'}>
              <input type="radio" bind:group={ovMode} value="auto" class="sr-only" />
              {autoLabel}
            </label>
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-center"
              class:border-accent={ovMode === 'new'}
              class:border-line={ovMode !== 'new'}
              class:bg-accent={ovMode === 'new'}
              class:text-accent-fg={ovMode === 'new'}
              class:font-semibold={ovMode === 'new'}>
              <input type="radio" bind:group={ovMode} value="new" class="sr-only" />
              Álbum/playlist nuevo
            </label>
            <label class="flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 text-center"
              class:border-accent={ovMode === 'existing'}
              class:border-line={ovMode !== 'existing'}
              class:bg-accent={ovMode === 'existing'}
              class:text-accent-fg={ovMode === 'existing'}
              class:font-semibold={ovMode === 'existing'}>
              <input type="radio" bind:group={ovMode} value="existing" class="sr-only" />
              Añadir a uno tuyo
            </label>
          </div>

          {#if ovMode === 'auto'}
            <p class="rounded-lg border border-line bg-surface p-3 text-xs text-fg-muted">
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
                <span class="text-xs text-fg-muted">Álbum</span>
                <input
                  type="text"
                  bind:value={ovAlbum}
                  placeholder="Nombre del álbum (vacío → Singles)"
                  class="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-fg-muted">
                  {preview.kind === 'playlist' ? 'Artista de la playlist' : 'Artista'}
                </span>
                <input
                  type="text"
                  bind:value={ovArtist}
                  placeholder="Nombre del artista"
                  class="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
                />
              </label>
              <label class="block">
                <span class="text-xs text-fg-muted">Año <span class="text-fg-subtle">(opcional)</span></span>
                <input
                  type="number"
                  bind:value={ovYear}
                  placeholder="2024"
                  min="1900"
                  max="2100"
                  class="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
                />
              </label>
            </div>
          {:else}
            <div class="text-sm">
              {#if albums.length === 0}
                <p class="rounded-lg border border-line bg-surface p-3 text-xs text-fg-subtle">
                  No tienes álbumes todavía. Crea uno nuevo primero.
                </p>
              {:else}
                <label class="block">
                  <span class="text-xs text-fg-muted">Álbum existente</span>
                  <select
                    bind:value={ovTargetAlbumId}
                    class="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
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

      <div class="border-t border-line bg-surface p-3">
        <button
          onclick={onImport}
          disabled={busy || selectedCount === 0 || (ovMode === 'existing' && !ovTargetAlbumId)}
          class="w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:bg-accent-hover disabled:opacity-50 min-h-11 sm:min-h-10"
        >
          {busy ? 'Encolando…' : `Importar ${selectedCount} ${selectedCount === 1 ? 'pista' : 'pistas'}`}
        </button>
      </div>

      {#if preview.tracks.length > 1}
        <div class="border-t border-line">
          <div class="flex items-center justify-between px-4 py-2 text-xs">
            <span class="text-fg-muted">{selectedCount} de {preview.tracks.length} seleccionadas</span>
            <button
              type="button"
              onclick={() => toggleAll(!allSelected)}
              class="font-medium text-accent hover:underline"
            >{allSelected ? 'Quitar todas' : 'Marcar todas'}</button>
          </div>
          <ul class="max-h-72 divide-y divide-line overflow-y-auto text-sm">
            {#each preview.tracks as t (t.spotify_id)}
              <li>
                <label class="flex cursor-pointer items-center gap-3 px-4 py-1.5 hover:bg-bg">
                  <input
                    type="checkbox"
                    bind:checked={selected[t.spotify_id]}
                    class="size-4 flex-none accent-accent"
                  />
                  <span class="min-w-0 flex-1 truncate" class:text-fg-subtle={!selected[t.spotify_id]}>
                    {t.title}
                  </span>
                  <span class="flex-none tabular-nums text-xs text-fg-subtle">{formatDuration(t.duration_ms)}</span>
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
  <section class="mt-12">
    <header class="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 class="section-title">
        Cola de descarga
      </h2>
      <div class="flex flex-wrap gap-1.5 text-xs">
        {#if jobs.stats.failed > 0}
          <button
            onclick={retryAllFailed}
            class="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-2 transition hover:bg-surface-2 min-h-11 sm:min-h-10"
          ><RefreshCw size={12} /> reintentar {jobs.stats.failed} fallidos</button>
          <button
            onclick={clearFailed}
            class="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-2 transition hover:bg-surface-2 min-h-11 sm:min-h-10"
          ><Trash2 size={12} /> borrar fallidos</button>
        {/if}
        {#if jobs.stats.done > 0}
          <button
            onclick={clearDone}
            class="rounded-lg border border-line px-2 py-2 text-fg-subtle hover:bg-surface-2 min-h-11 sm:min-h-10"
          >limpiar historial</button>
        {/if}
      </div>
    </header>

    <div class="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2 text-xs min-h-11 sm:min-h-10">
      <span class="text-fg-muted">Total: <b class="text-fg">{jobs.stats.total}</b></span>
      {#if jobs.stats.pending > 0}
        <span class="inline-flex items-center gap-1 text-fg-muted"><Clock size={11} /> {jobs.stats.pending}</span>
      {/if}
      {#if jobs.stats.running > 0}
        <span class="inline-flex items-center gap-1 text-accent"><Loader2 size={11} class="animate-spin" /> {jobs.stats.running}</span>
      {/if}
      {#if jobs.stats.done > 0}
        <span class="inline-flex items-center gap-1 text-accent"><Check size={11} /> {jobs.stats.done}</span>
      {/if}
      {#if jobs.stats.failed > 0}
        <span class="inline-flex items-center gap-1 text-danger"><X size={11} /> {jobs.stats.failed}</span>
      {/if}
      {#if jobs.active > 0}
        <span class="ml-auto inline-flex items-center gap-1 text-accent">
          <span class="size-1.5 animate-pulse rounded-full bg-accent"></span>
          descargando…
        </span>
      {/if}
    </div>

    {#if groups.length === 0}
      <div class="rounded-lg border border-dashed border-line p-8 text-center">
        <p class="text-sm text-fg-muted">Sin importaciones todavía.</p>
        <p class="mt-2 text-xs text-fg-subtle">
          Prueba pegando una URL: <br />
          spotify.com · youtube.com · soundcloud.com
        </p>
      </div>
    {:else}
      <ul class="space-y-2">
        {#each groups as g (g.key)}
          {@const total = g.items.length}
          {@const isOpen = expanded[g.key] ?? false}
          <li class="overflow-hidden rounded-lg border border-line bg-surface">
            <button
              type="button"
              onclick={() => (expanded[g.key] = !isOpen)}
              class="flex w-full items-center gap-3 p-3 text-left hover:bg-surface-2/50"
            >
              {#if g.cover_url}
                <img loading="lazy" decoding="async" src={g.cover_url} alt="" class="size-12 flex-none rounded-lg object-cover" />
              {:else}
                <div class="grid size-12 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
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
                  <span class="text-xs uppercase text-fg-subtle">{kindLabel(g.kind)}</span>
                  <span class="truncate text-sm font-medium">{g.name}</span>
                </div>
                <div class="mt-1 flex flex-wrap items-center gap-2 text-xs">
                  <span class="block h-1 w-20 overflow-hidden rounded-full bg-surface-2">
                    <span
                      class="block h-full bg-accent"
                      style:width="{total > 0 ? Math.round((g.counts.done / total) * 100) : 0}%"
                    ></span>
                  </span>
                  <span class="text-fg-subtle">{g.counts.done}/{total}</span>
                  {#if g.counts.running > 0}
                    <span class="inline-flex items-center gap-0.5 text-accent">
                      <Loader2 size={10} class="animate-spin" /> {g.counts.running}
                    </span>
                  {/if}
                  {#if g.counts.failed > 0}
                    <span class="inline-flex items-center gap-0.5 text-danger">
                      <X size={10} /> {g.counts.failed}
                    </span>
                  {/if}
                </div>
              </div>
              <span class="text-fg-subtle">
                {#if isOpen}<ChevronDown size={16} />{:else}<ChevronRight size={16} />{/if}
              </span>
            </button>

            {#if isOpen}
              <ul class="divide-y divide-line border-t border-line bg-bg">
                {#each g.items as job (job.id)}
                  {@const StatusIcon = STATUS_ICON[job.status]}
                  <li class="px-3 py-2">
                    <div class="flex items-center gap-3">
                      <span class="flex w-5 flex-none items-center justify-center {statusColor(job.status)}">
                        <StatusIcon size={14} class={job.status === 'running' ? 'animate-spin' : ''} />
                      </span>
                      <div class="min-w-0 flex-1">
                        <div class="truncate text-sm">{job.title}</div>
                        <div class="truncate text-xs text-fg-subtle">
                          {job.artist}
                          {#if job.album} · {job.album}{/if}
                          {#if job.backend_used} · {job.backend_used}{/if}
                          {#if job.duration_ms} · {formatDuration(job.duration_ms)}{/if}
                        </div>
                        {#if job.error}
                          <div class="mt-0.5 truncate text-xs text-danger/80" title={job.error}>{job.error}</div>
                        {/if}
                      </div>
                      <div class="flex flex-none gap-1">
                        {#if job.status === 'failed'}
                          <button
                            onclick={() => retry(job.id)}
                            class="grid size-10 place-items-center rounded-lg border border-line transition hover:bg-surface-2"
                            title="Reintentar"
                          ><RefreshCw size={12} /></button>
                        {/if}
                        {#if job.status !== 'running'}
                          <button
                            onclick={() => remove(job.id)}
                            class="grid size-10 place-items-center rounded-lg border border-line text-fg-subtle transition hover:bg-surface-2 hover:text-danger"
                            title="Eliminar"
                          ><X size={12} /></button>
                        {/if}
                      </div>
                    </div>
                    {#if job.status === 'running'}
                      <div class="mt-1.5 ml-8 flex items-center gap-2 text-xs text-accent">
                        <span class="relative block h-1 flex-1 overflow-hidden rounded-full bg-surface-2">
                          <span
                            class="block h-full bg-accent transition-all duration-500"
                            style:width="{Math.max(2, job.progress)}%"
                          ></span>
                          <!-- Stripe indeterminado encima cuando estamos atascados en 95% (convirtiendo) -->
                          {#if job.progress >= 90 && job.progress < 100}
                            <span class="absolute inset-0 animate-pulse bg-accent-hover/30"></span>
                          {/if}
                        </span>
                        <span class="w-9 text-right tabular-nums">{job.progress}%</span>
                        {#if job.stage}
                          <span class="text-fg-subtle">· {job.stage}</span>
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
