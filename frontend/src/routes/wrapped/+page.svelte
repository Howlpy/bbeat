<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import { coverSrc } from '$lib/cover';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import {
    Flame,
    Clock,
    Users,
    Music2,
    Trophy,
    Share2,
    CalendarClock,
    TrendingUp,
    TrendingDown
  } from 'lucide-svelte';
  import { toPng } from 'html-to-image';
  import { api, type MyStats } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import { auth } from '$lib/auth.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import WrappedCard from '$lib/components/WrappedCard.svelte';

  const RANGES = [
    { label: 'Semana', days: 7 as number | undefined },
    { label: 'Mes', days: 30 as number | undefined },
    { label: 'Año', days: 365 as number | undefined },
    { label: 'Todo', days: undefined }
  ];

  let stats = $state<MyStats | null>(null);
  let rangeIdx = $state(3); // por defecto "Todo"
  let loading = $state(true);
  let error = $state<string | null>(null);
  let sharing = $state(false);
  let cardEl = $state<HTMLDivElement | null>(null);

  const rangeLabel = $derived(RANGES[rangeIdx].label);
  const clockMax = $derived(stats ? Math.max(1, ...stats.clock) : 1);

  async function load() {
    loading = true;
    error = null;
    try {
      stats = await api.myStats(RANGES[rangeIdx].days);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  function setRange(i: number) {
    if (i === rangeIdx) return;
    rangeIdx = i;
    load();
  }

  onMount(() => {
    load();
    return onReconnect(() => {
      if (error) load();
    });
  });

  function pct(cur: number, prev: number): number | null {
    if (!prev) return null;
    return Math.round(((cur - prev) / prev) * 100);
  }

  function fmtDate(iso: string | null): string {
    if (!iso) return '—';
    return new Date(iso + 'Z').toLocaleDateString('es-ES', {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  }

  async function share() {
    if (!cardEl) return;
    sharing = true;
    try {
      const dataUrl = await toPng(cardEl, { pixelRatio: 2, cacheBust: true });
      const blob = await (await fetch(dataUrl)).blob();
      const file = new File([blob], 'bbeat-wrapped.png', { type: 'image/png' });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: 'Mi Wrapped de bbeat' });
      } else {
        const a = document.createElement('a');
        a.href = dataUrl;
        a.download = 'bbeat-wrapped.png';
        a.click();
      }
    } catch {
      /* el usuario canceló el share o falló la captura */
    } finally {
      sharing = false;
    }
  }
</script>

<div class="page-narrow">
  <BackButton fallback="/" />
  <header class="mb-6 flex items-center gap-4">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-accent-soft text-accent">
      <Flame size={24} />
    </span>
    <div>
      <h1 class="page-title">Tu Wrapped</h1>
      <p class="text-sm text-fg-muted">tus números en bbeat</p>
    </div>
  </header>

  <!-- Selector de rango -->
  <div class="mb-8 inline-flex rounded-lg bg-surface p-1">
    {#each RANGES as r, i}
      <button
        type="button"
        onclick={() => setRange(i)}
        class="min-h-10 rounded-md px-4 text-sm font-medium transition sm:min-h-9"
        class:bg-accent={i === rangeIdx}
        class:text-accent-fg={i === rangeIdx}
        class:text-fg-muted={i !== rangeIdx}
      >{r.label}</button>
    {/each}
  </div>

  {#if error}
    <ErrorState {error} />
  {:else if loading}
    <div class="grid grid-cols-3 gap-3"><Skeleton class="h-28" /><Skeleton class="h-28" /><Skeleton class="h-28" /></div>
    <Skeleton class="mt-6 h-32 w-full" />
  {:else if stats && stats.total_plays === 0}
    <EmptyState icon={Flame} title="Sin reproducciones en este periodo" text="Prueba otro rango o dale al play." />
  {:else if stats}
    {@const dPlays = stats.prev ? pct(stats.total_plays, stats.prev.plays) : null}
    {@const dMin = stats.prev ? pct(stats.total_minutes, stats.prev.minutes) : null}

    <!-- Hero -->
    <section class="mb-4 grid grid-cols-3 gap-3">
      <div class="rounded-xl border border-accent/40 bg-accent-soft p-4 text-center">
        <Flame size={18} class="mx-auto mb-1 text-accent" />
        <div class="text-2xl font-bold tabular-nums text-accent">{stats.total_plays}</div>
        <div class="text-xs uppercase tracking-wider text-fg-subtle">plays</div>
        {#if dPlays !== null}
          <div class="mt-1 flex items-center justify-center gap-0.5 text-xs" class:text-success={dPlays >= 0} class:text-danger={dPlays < 0}>
            {#if dPlays >= 0}<TrendingUp size={11} />{:else}<TrendingDown size={11} />{/if}
            {Math.abs(dPlays)}%
          </div>
        {/if}
      </div>
      <div class="rounded-xl border border-line bg-surface p-4 text-center">
        <Clock size={18} class="mx-auto mb-1 text-fg-muted" />
        <div class="text-2xl font-bold tabular-nums">{stats.total_minutes}</div>
        <div class="text-xs uppercase tracking-wider text-fg-subtle">minutos</div>
        {#if dMin !== null}
          <div class="mt-1 flex items-center justify-center gap-0.5 text-xs" class:text-success={dMin >= 0} class:text-danger={dMin < 0}>
            {#if dMin >= 0}<TrendingUp size={11} />{:else}<TrendingDown size={11} />{/if}
            {Math.abs(dMin)}%
          </div>
        {/if}
      </div>
      <div class="rounded-xl border border-line bg-surface p-4 text-center">
        <Music2 size={18} class="mx-auto mb-1 text-fg-muted" />
        <div class="text-2xl font-bold tabular-nums">{stats.unique_tracks}</div>
        <div class="text-xs uppercase tracking-wider text-fg-subtle">pistas</div>
      </div>
    </section>

    <!-- Racha + primer/último play -->
    <section class="mb-10 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-warning/40 bg-warning/10 p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-fg-subtle">
          <Flame size={13} class="text-warning" /> Racha
        </div>
        <div class="text-xl font-bold text-warning">
          {stats.streak_days} {stats.streak_days === 1 ? 'día' : 'días'}
        </div>
      </div>
      <div class="rounded-xl border border-line bg-surface p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-fg-subtle">
          <CalendarClock size={13} /> Primer play
        </div>
        <div class="text-sm font-semibold">{fmtDate(stats.first_play)}</div>
      </div>
      <div class="rounded-xl border border-line bg-surface p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-fg-subtle">
          <CalendarClock size={13} /> Último play
        </div>
        <div class="text-sm font-semibold">{fmtDate(stats.last_play)}</div>
      </div>
    </section>

    <!-- Reloj de escucha -->
    <section class="mb-10">
      <h2 class="section-title mb-3">
        <Clock size={14} class="text-accent" /> Reloj de escucha
      </h2>
      <div class="rounded-xl border border-line bg-surface p-4">
        <div class="flex h-24 items-end gap-[3px]">
          {#each stats.clock as c, h}
            <div class="group relative flex-1" title="{h}:00 · {c} plays">
              <div
                class="w-full rounded-t bg-accent transition-all group-hover:bg-accent-hover"
                style:height="{Math.max(2, (c / clockMax) * 88)}px"
              ></div>
            </div>
          {/each}
        </div>
        <div class="mt-1.5 flex justify-between text-xs text-fg-subtle">
          <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
        </div>
      </div>
    </section>

    <!-- Tus top tracks -->
    {#if stats.top_tracks.length > 0}
      <section class="mb-10">
        <h2 class="section-title mb-3">
          <Trophy size={14} class="text-accent" /> Tus más escuchadas
        </h2>
        <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {#each stats.top_tracks as t, i (t.id)}
            <li>
              <button
                onclick={() => stats && player.playTracks(stats.top_tracks, i)}
                class="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
              >
                <span class="w-5 flex-none text-center text-xs tabular-nums text-fg-subtle">{i + 1}</span>
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={coverSrc(t.cover_url, 96)} alt="" class="size-10 flex-none rounded-lg object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle"><Music2 size={14} /></div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-fg-subtle">{t.artist_name}</div>
                </div>
                <span class="flex-none text-xs text-fg-subtle">{t.plays}×</span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Tus top artistas -->
    {#if stats.top_artists.length > 0}
      <section class="mb-10">
        <h2 class="section-title mb-3">
          <Users size={14} class="text-accent" /> Tus artistas top
        </h2>
        <div class="flex flex-wrap gap-2">
          {#each stats.top_artists as a, i (a.id)}
            <a
              href="/artists/{a.id}"
              class="inline-flex min-h-10 items-center gap-2 rounded-full border border-line bg-surface px-4 text-sm transition hover:bg-surface-2"
            >
              <span class="text-xs tabular-nums text-fg-subtle">{i + 1}</span>
              {a.name}
              <span class="text-xs text-accent">{a.plays}×</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Tarjeta compartible -->
    <section>
      <h2 class="section-title mb-3">
        <Share2 size={14} class="text-accent" /> Comparte tu wrapped
      </h2>
      <div class="flex flex-col items-center gap-4">
        <div bind:this={cardEl}>
          <WrappedCard {stats} username={auth.user?.username ?? 'bbeat'} {rangeLabel} />
        </div>
        <Button variant="primary" onclick={share} disabled={sharing}>
          <Share2 size={16} /> {sharing ? 'Generando…' : 'Compartir imagen'}
        </Button>
      </div>
    </section>
  {/if}
</div>
