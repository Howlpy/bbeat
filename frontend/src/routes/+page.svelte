<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Download,
    Disc3,
    Music2,
    Play,
    Search,
    RefreshCw,
    AudioWaveform,
    Flame,
    Heart,
    WifiOff,
    HardDriveDownload,
    Radio
  } from 'lucide-svelte';
  import {
    api,
    formatBytes,
    formatDuration,
    type Album,
    type LibraryStats,
    type NowPlaying,
    type Track
  } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { jobs } from '$lib/jobs.svelte';
  import { player } from '$lib/player.svelte';
  import { offline } from '$lib/offline.svelte';
  import { isOfflineError } from '$lib/net.svelte';

  let stats = $state<LibraryStats | null>(null);
  let recentTracks = $state<Track[]>([]);
  let recentAlbums = $state<Album[]>([]);
  let topTracks = $state<(Track & { plays: number })[]>([]);
  let live = $state<NowPlaying[]>([]);
  let error = $state<string | null>(null);
  let offlineMode = $state(false);
  let scanning = $state(false);

  async function load() {
    try {
      const [s, r, top] = await Promise.all([
        api.stats(),
        api.recent(12),
        api.topTracks({ limit: 8 }).catch(() => ({ items: [] }))
      ]);
      stats = s;
      recentTracks = r.tracks ?? [];
      recentAlbums = r.albums ?? [];
      topTracks = top.items ?? [];
    } catch (e) {
      if (isOfflineError(e)) offlineMode = true;
      else error = e instanceof Error ? e.message : String(e);
    }
  }

  async function rescan() {
    scanning = true;
    try {
      await api.startScan();
      let s = await api.scanStatus();
      while (s.running) {
        await new Promise((r) => setTimeout(r, 700));
        s = await api.scanStatus();
      }
      await load();
    } finally {
      scanning = false;
    }
  }

  function playRecentTrack(i: number) {
    player.playTracks(recentTracks, i);
  }

  function playTopTrack(i: number) {
    player.playTracks(topTracks, i);
  }

  onMount(() => {
    load();
    // Feed en vivo "sonando ahora" (se cierra al salir de la home).
    const es = api.nowPlayingStream((items) => (live = items));
    return () => es.close();
  });

  const greeting = $derived.by(() => {
    const h = new Date().getHours();
    if (h < 6) return 'Buenas noches';
    if (h < 13) return 'Buenos días';
    if (h < 21) return 'Buenas tardes';
    return 'Buenas noches';
  });
</script>

<div class="mx-auto max-w-5xl px-4 pt-6 pb-8 sm:pt-10">
  <header class="mb-6 flex items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img src="/icon.svg?v=2" alt="bbeat" class="size-11 flex-none rounded-xl" />
      <div class="min-w-0">
        <p class="truncate text-xs uppercase tracking-widest text-slate-500">{greeting}</p>
        <h1 class="truncate text-3xl font-bold tracking-tight">
          {auth.user?.username ?? 'Bbeat'}
        </h1>
      </div>
    </div>
    {#if auth.user?.is_admin}
      <span class="flex-none rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan-400">
        admin
      </span>
    {/if}
  </header>

  {#if offlineMode}
    <div class="rounded-xl border border-slate-800 bg-slate-900 p-6 text-center">
      <WifiOff class="mx-auto mb-2 text-slate-500" size={30} />
      <p class="text-sm text-slate-300">Sin conexión.</p>
      <p class="mt-1 text-xs text-slate-500">Tus canciones descargadas siguen disponibles sin internet.</p>
      <a
        href="/downloads"
        class="mt-4 inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
      ><HardDriveDownload size={16} /> Ir a Descargas</a>
    </div>
  {:else if error}
    <p class="rounded border border-red-900/50 bg-red-950/50 p-3 text-sm text-red-300">{error}</p>
  {:else if !stats}
    <p class="text-slate-500">Cargando…</p>
  {:else}
    <!-- Banner de actividad -->
    {#if jobs.active > 0}
      <a
        href="/import"
        class="mb-5 flex items-center gap-3 rounded border border-cyan-900/40 bg-cyan-950/30 p-3 text-sm transition hover:bg-cyan-950/50"
      >
        <span class="grid size-8 flex-none place-items-center rounded-full bg-cyan-500/20">
          <AudioWaveform size={16} class="text-cyan-400" />
        </span>
        <span class="flex-1">
          <b class="text-cyan-300">{jobs.stats.running}</b> descargando ·
          <b class="text-cyan-300">{jobs.stats.pending}</b> en cola
        </span>
        <span class="text-xs text-cyan-400">ver →</span>
      </a>
    {/if}

    <!-- Resumen: pistas en la app + descargas offline -->
    <section class="mb-6 grid grid-cols-2 gap-3">
      <a
        href="/library"
        class="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-cyan-700/50 hover:bg-slate-800/70"
      >
        <div class="mb-2 flex items-center gap-2 text-slate-500">
          <Music2 size={15} />
          <span class="text-xs uppercase tracking-wider">canciones</span>
        </div>
        <div class="text-3xl font-bold text-cyan-400">{stats.tracks}</div>
        <div class="mt-0.5 text-xs text-slate-500">en la app</div>
      </a>
      <a
        href="/downloads"
        class="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-cyan-700/50 hover:bg-slate-800/70"
      >
        <div class="mb-2 flex items-center gap-2 text-slate-500">
          <HardDriveDownload size={15} />
          <span class="text-xs uppercase tracking-wider">descargas</span>
        </div>
        <div class="text-3xl font-bold">{offline.ids.size}</div>
        <div class="mt-0.5 text-xs text-slate-500">{formatBytes(offline.totalBytes)} sin conexión</div>
      </a>
    </section>

    <!-- Acciones rápidas -->
    <section class="mb-8 flex flex-wrap gap-2">
      <a
        href="/import"
        class="inline-flex items-center gap-2 rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
      >
        <Download size={16} /> Importar
      </a>
      <a
        href="/library"
        class="inline-flex items-center gap-2 rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-900"
      >
        <Search size={16} /> Buscar
      </a>
      <a
        href="/liked"
        class="inline-flex items-center gap-2 rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-900"
      >
        <Heart size={16} /> Favoritos
      </a>
      <a
        href="/wrapped"
        class="inline-flex items-center gap-2 rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-900"
      >
        <Flame size={16} /> Wrapped
      </a>
      {#if auth.user?.is_admin}
        <button
          onclick={rescan}
          disabled={scanning}
          class="inline-flex items-center gap-2 rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-900 disabled:opacity-50"
        >
          <RefreshCw size={16} class={scanning ? 'animate-spin' : ''} />
          {scanning ? 'Escaneando…' : 'Re-escanear disco'}
        </button>
      {/if}
    </section>

    {#if stats.tracks === 0}
      <p class="mb-8 rounded border border-amber-900/50 bg-amber-950/30 p-4 text-sm text-amber-200">
        Tu biblioteca está vacía. Pega una URL en
        <a href="/import" class="underline">/import</a> para empezar.
      </p>
    {/if}

    <!-- Sonando ahora (en vivo) -->
    {#if live.length > 0}
      <section class="mb-8">
        <header class="mb-3 flex items-baseline justify-between">
          <h2 class="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
            <Radio size={14} class="text-fuchsia-400" />
            <span class="relative flex items-center gap-1.5">
              Sonando ahora
              <span class="inline-block size-2 animate-pulse rounded-full bg-emerald-500"></span>
            </span>
          </h2>
          <a href="/live" class="text-xs text-fuchsia-400 hover:underline">ver todo →</a>
        </header>
        <ul class="space-y-1.5">
          {#each live.slice(0, 3) as p (p.user_id)}
            <li class="flex items-center gap-3 rounded border border-slate-800/60 bg-slate-900/40 px-3 py-2">
              {#if p.track.cover_url}
                <img loading="lazy" decoding="async" src={p.track.cover_url} alt="" class="size-9 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-9 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={13} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{p.track.title}</div>
                <div class="truncate text-xs text-slate-500">
                  <span class="text-fuchsia-400">{p.username}</span> · {p.track.artist_name}
                </div>
              </div>
              <button
                onclick={() => player.playTracks([p.track], 0)}
                class="grid size-8 flex-none place-items-center rounded-full text-fuchsia-400 transition hover:bg-slate-800"
                title="Reproducir"
              ><Play size={14} fill="currentColor" /></button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Álbumes recientes -->
    {#if recentAlbums.length > 0}
      <section class="mb-8">
        <header class="mb-3 flex items-baseline justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Añadidos recientemente
          </h2>
          <a href="/albums" class="text-xs text-cyan-400 hover:underline">ver todos →</a>
        </header>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {#each recentAlbums.slice(0, 6) as album (album.id)}
            <a href="/albums/{album.id}" class="group">
              {#if album.cover_url}
                <img loading="lazy" decoding="async"
                  src={album.cover_url}
                  alt={album.title}
                  class="aspect-square w-full rounded object-cover transition group-hover:opacity-80"
                />
              {:else}
                <div class="grid aspect-square w-full place-items-center rounded bg-slate-800 text-slate-700">
                  <Disc3 size={36} />
                </div>
              {/if}
              <div class="mt-1.5 truncate text-sm font-medium">{album.title}</div>
              <div class="truncate text-xs text-slate-500">{album.artist_name}</div>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Más escuchadas -->
    {#if topTracks.length > 0}
      <section class="mb-8">
        <header class="mb-3 flex items-baseline justify-between">
          <h2 class="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
            <Flame size={14} class="text-cyan-400" /> Tus más escuchadas
          </h2>
        </header>
        <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
          {#each topTracks as t, i (t.id)}
            {@const isCurrent = player.current?.id === t.id}
            <li>
              <button
                onclick={() => playTopTrack(i)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
                class:bg-slate-800={isCurrent}
              >
                <span class="w-5 flex-none text-center font-mono text-xs text-slate-600">{i + 1}</span>
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm" class:text-cyan-400={isCurrent}>{t.title}</div>
                  <div class="truncate text-xs text-slate-500">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="flex-none text-xs text-slate-500">
                  {t.plays} {t.plays === 1 ? 'play' : 'plays'}
                </span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Pistas recientes -->
    {#if recentTracks.length > 0}
      <section class="mb-8">
        <header class="mb-3 flex items-baseline justify-between">
          <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Pistas recientes
          </h2>
          <a href="/library" class="text-xs text-cyan-400 hover:underline">ver todas →</a>
        </header>
        <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
          {#each recentTracks.slice(0, 8) as t, i (t.id)}
            {@const isCurrent = player.current?.id === t.id}
            <li>
              <button
                onclick={() => playRecentTrack(i)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
                class:bg-slate-800={isCurrent}
              >
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm" class:text-cyan-400={isCurrent}>{t.title}</div>
                  <div class="truncate text-xs text-slate-500">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="hidden flex-none font-mono text-xs text-slate-500 sm:block">
                  {formatDuration(t.duration_ms)}
                </span>
                <span class="grid size-8 flex-none place-items-center rounded-full text-cyan-400 opacity-0 transition group-hover:opacity-100">
                  <Play size={14} fill="currentColor" />
                </span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>
