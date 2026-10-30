<script lang="ts">
  import { coverSrc } from '$lib/cover';
  import { onMount } from 'svelte';
  import {
    Disc3,
    Music2,
    Play,
    AudioWaveform,
    Flame,
    Heart,
    WifiOff,
    Radio,
    TrendingUp
  } from 'lucide-svelte';
  import {
    api,
    formatDuration,
    type Album,
    type ChartGenre,
    type LibraryStats,
    type NowPlaying,
    type Track
  } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { jobs } from '$lib/jobs.svelte';
  import { player } from '$lib/player.svelte';
  import { offline } from '$lib/offline.svelte';
  import { isOfflineError, onReconnect } from '$lib/net.svelte';
  import OfflineEmpty from '$lib/components/OfflineEmpty.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';

  let stats = $state<LibraryStats | null>(null);
  let recentTracks = $state<Track[]>([]);
  let recentAlbums = $state<Album[]>([]);
  let topTracks = $state<(Track & { plays: number })[]>([]);
  let charts = $state<ChartGenre[] | null>(null);
  let live = $state<NowPlaying[]>([]);
  let liveConnected = $state(false);
  let error = $state<string | null>(null);
  // Sin red y sin caché de esta página: vacío compacto dentro del layout normal.
  let offlineMode = $state(false);

  async function load() {
    try {
      const [s, r, top] = await Promise.all([
        api.stats(),
        api.recent(12),
        api.topTracks({ limit: 8 }).catch(() => ({ items: [] }))
      ]);
      stats = s;
      // Listas semanales: si fallan, la sección simplemente no aparece.
      api.charts().then((c) => (charts = c.items)).catch(() => (charts = charts ?? []));
      recentTracks = r.tracks ?? [];
      recentAlbums = r.albums ?? [];
      topTracks = top.items ?? [];
      offlineMode = false;
      error = null;
    } catch (e) {
      if (isOfflineError(e)) offlineMode = true;
      else error = e instanceof Error ? e.message : String(e);
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
    const offReconnect = onReconnect(load);
    // Cloudflare puede bufferizar SSE; refresca el snapshot cada 10 s.
    let stopped = false;
    let inFlight = false;
    const refreshLive = async () => {
      // Sin solapar peticiones (si una se cuelga, no se apilan) y con la app oculta no hace falta.
      if (inFlight || document.hidden) return;
      inFlight = true;
      try {
        const result = await api.nowPlayingSnapshot();
        if (!stopped) {
          live = result.items;
          liveConnected = true;
        }
      } catch {
        if (!stopped) liveConnected = false;
      } finally {
        inFlight = false;
      }
    };
    refreshLive();
    const liveTimer = setInterval(refreshLive, 10_000);
    return () => {
      stopped = true;
      offReconnect();
      clearInterval(liveTimer);
    };
  });

  const greeting = $derived.by(() => {
    const h = new Date().getHours();
    if (h < 6) return 'Buenas noches';
    if (h < 13) return 'Buenos días';
    if (h < 21) return 'Buenas tardes';
    return 'Buenas noches';
  });
</script>

<div class="page">
  <header class="mb-8 flex items-center justify-between gap-3">
    <div class="flex min-w-0 items-center gap-3">
      <img src="/icon.svg?v=2" alt="bbeat" class="size-11 flex-none rounded-xl" />
      <div class="min-w-0">
        <p class="truncate text-xs uppercase tracking-widest text-fg-subtle">{greeting}</p>
        <h1 class="truncate text-2xl font-bold tracking-tight sm:text-3xl">
          {auth.user?.username ?? 'Bbeat'}
        </h1>
      </div>
    </div>
    {#if auth.user?.is_admin}
      <span class="flex-none rounded-lg border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-accent">
        admin
      </span>
    {/if}
  </header>

  {#if offlineMode}
    <OfflineEmpty />
  {:else if error}
    <ErrorState {error} />
  {:else if !stats}
    <div class="grid grid-cols-2 gap-3">
      <Skeleton class="h-28" /><Skeleton class="h-28" />
    </div>
    <div class="mt-8 space-y-2">
      {#each Array(5) as _}<Skeleton class="h-14 w-full" />{/each}
    </div>
  {:else}
    <!-- Banner de actividad -->
    {#if jobs.active > 0}
      <a
        href="/import"
        class="mb-8 flex items-center gap-3 rounded-xl border border-accent/40 bg-accent-soft p-3 text-sm transition hover:border-accent"
      >
        <span class="grid size-8 flex-none place-items-center rounded-full bg-accent/20">
          <AudioWaveform size={16} class="text-accent" />
        </span>
        <span class="flex-1">
          <b class="text-accent">{jobs.stats.running}</b> descargando ·
          <b class="text-accent">{jobs.stats.pending}</b> en cola
        </span>
        <span class="text-xs text-accent">ver →</span>
      </a>
    {/if}

    <!-- Resumen compacto + accesos -->
    <section class="mb-8 flex flex-wrap items-center gap-2">
      <a
        href="/library"
        class="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm transition hover:border-line-strong hover:bg-surface-2"
      ><Music2 size={15} class="text-accent" /> <b class="tabular-nums">{stats.tracks}</b> canciones</a>
      <a
        href="/liked"
        class="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm transition hover:border-line-strong hover:bg-surface-2"
      ><Heart size={15} class="text-accent" /> Favoritos</a>
      <a
        href="/wrapped"
        class="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm transition hover:border-line-strong hover:bg-surface-2"
      ><Flame size={15} class="text-accent" /> Wrapped</a>
    </section>

    {#if stats.tracks === 0}
      <p class="mb-8 rounded-xl border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
        Tu biblioteca está vacía. Pega una URL en
        <a href="/import" class="underline">/import</a> para empezar.
      </p>
    {/if}

    <!-- Lo más escuchado esta semana (una tarjeta por género) -->
    {#if charts === null}
      <section class="mb-10" aria-hidden="true">
        <Skeleton class="mb-3 h-4 w-52" />
        <div class="flex gap-3 overflow-hidden">
          {#each Array(3) as _}<Skeleton class="h-44 w-40 flex-none rounded-xl" />{/each}
        </div>
      </section>
    {:else if charts.length > 0}
      <section class="mb-10">
        <header class="mb-3">
          <h2 class="section-title">
            <TrendingUp size={14} class="text-accent" /> Lo más escuchado esta semana
          </h2>
        </header>
        <div class="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
          {#each charts as g (g.genre)}
            <a
              href="/charts/{encodeURIComponent(g.genre)}"
              class="w-40 flex-none snap-start rounded-xl border border-line bg-surface p-2.5 transition hover:border-line-strong hover:bg-surface-2"
            >
              <div class="grid aspect-square grid-cols-2 gap-0.5 overflow-hidden rounded-lg bg-surface-2">
                {#if g.covers.length >= 4}
                  {#each g.covers.slice(0, 4) as c}
                    <img loading="lazy" decoding="async" src={coverSrc(c, 96)} alt="" class="size-full object-cover" />
                  {/each}
                {:else if g.covers.length > 0}
                  <img loading="lazy" decoding="async" src={coverSrc(g.covers[0], 192)} alt="" class="col-span-2 row-span-2 size-full object-cover" />
                {:else}
                  <div class="col-span-2 row-span-2 grid place-items-center text-fg-subtle"><Music2 size={32} /></div>
                {/if}
              </div>
              <div class="mt-2 truncate text-sm font-semibold">Top {g.name}</div>
              <div class="truncate text-xs text-fg-subtle">{g.track_count} canciones · últimos 7 días</div>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Escuchando ahora (stream en vivo) -->
    <section class="mb-10">
      <header class="mb-3 flex items-center justify-between">
        <h2 class="section-title">
          <Radio size={14} class="text-accent" />
          <span class="relative flex items-center gap-1.5">
            Escuchando ahora…
            <span
              class="inline-block size-2 rounded-full {liveConnected ? 'animate-pulse bg-success' : 'bg-line-strong'}"
              title={liveConnected ? 'Actualización en directo' : 'Reconectando'}
            ></span>
          </span>
        </h2>
        <a href="/live" class="inline-flex min-h-10 items-center text-sm text-accent hover:underline">ver todo →</a>
      </header>
      {#if live.length > 0}
        <ul class="space-y-1.5">
          {#each live.slice(0, 3) as p (p.user_id)}
            <li class="flex items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2">
              {#if p.track.cover_url}
                <img loading="lazy" decoding="async" src={coverSrc(p.track.cover_url, 96)} alt="" class="size-9 flex-none rounded-lg object-cover" />
              {:else}
                <div class="grid size-9 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle"><Music2 size={13} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{p.track.title}</div>
                <div class="truncate text-xs text-fg-subtle">
                  <span class="text-accent">{p.username}</span> · {p.track.artist_name}
                </div>
              </div>
              <button
                onclick={() => player.playTracks([p.track], 0)}
                class="grid size-10 flex-none place-items-center rounded-full text-accent transition hover:bg-surface-2"
                title="Reproducir"
              ><Play size={14} fill="currentColor" /></button>
            </li>
          {/each}
        </ul>
      {:else}
        <div class="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-fg-muted">
          {liveConnected ? 'Ahora mismo no hay nadie escuchando.' : 'Conectando con la actividad en directo…'}
        </div>
      {/if}
    </section>

    <!-- Álbumes recientes -->
    {#if recentAlbums.length > 0}
      <section class="mb-10">
        <header class="mb-3 flex items-center justify-between">
          <h2 class="section-title">
            Añadidos recientemente
          </h2>
          <a href="/albums" class="inline-flex min-h-10 items-center text-sm text-accent hover:underline">ver todos →</a>
        </header>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {#each recentAlbums.slice(0, 6) as album (album.id)}
            <a href="/albums/{album.id}" class="group">
              {#if album.cover_url}
                <img loading="lazy" decoding="async"
                  src={coverSrc(album.cover_url, 384)}
                  alt={album.title}
                  class="aspect-square w-full rounded-xl object-cover transition active:opacity-80 group-hover:opacity-90"
                />
              {:else}
                <div class="grid aspect-square w-full place-items-center rounded-xl bg-surface-2 text-fg-subtle">
                  <Disc3 size={36} />
                </div>
              {/if}
              <div class="mt-2 truncate text-sm font-semibold">{album.title}</div>
              <div class="truncate text-xs text-fg-subtle">{album.artist_name}</div>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Más escuchadas -->
    {#if topTracks.length > 0}
      <section class="mb-10">
        <header class="mb-3 flex items-center justify-between">
          <h2 class="section-title">
            <Flame size={14} class="text-accent" /> Tus más escuchadas
          </h2>
        </header>
        <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {#each topTracks as t, i (t.id)}
            {@const isCurrent = player.current?.id === t.id}
            <li>
              <button
                onclick={() => playTopTrack(i)}
                class="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
                class:bg-surface-2={isCurrent}
                class:opacity-40={!offline.canPlay(t.id)}
              >
                <span class="w-5 flex-none text-center text-xs tabular-nums text-fg-subtle">{i + 1}</span>
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={coverSrc(t.cover_url, 96)} alt="" class="size-10 flex-none rounded-lg object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm" class:text-accent={isCurrent}>{t.title}</div>
                  <div class="truncate text-xs text-fg-subtle">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="flex-none text-xs tabular-nums text-fg-subtle">
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
      <section class="mb-10">
        <header class="mb-3 flex items-center justify-between">
          <h2 class="section-title">
            Pistas recientes
          </h2>
          <a href="/library" class="inline-flex min-h-10 items-center text-sm text-accent hover:underline">ver todas →</a>
        </header>
        <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {#each recentTracks.slice(0, 8) as t, i (t.id)}
            {@const isCurrent = player.current?.id === t.id}
            <li>
              <button
                onclick={() => playRecentTrack(i)}
                class="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
                class:bg-surface-2={isCurrent}
                class:opacity-40={!offline.canPlay(t.id)}
              >
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={coverSrc(t.cover_url, 96)} alt="" class="size-10 flex-none rounded-lg object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
                    <Music2 size={14} />
                  </div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm" class:text-accent={isCurrent}>{t.title}</div>
                  <div class="truncate text-xs text-fg-subtle">
                    {t.artist_name}{#if t.album_title} · {t.album_title}{/if}
                  </div>
                </div>
                <span class="hidden flex-none text-xs tabular-nums text-fg-subtle sm:block">
                  {formatDuration(t.duration_ms)}
                </span>
                <span class="grid size-8 flex-none place-items-center rounded-full text-fg-subtle">
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
