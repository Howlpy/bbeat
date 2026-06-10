<script lang="ts">
  import { onMount } from 'svelte';
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

  onMount(load);

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

<div class="mx-auto max-w-3xl px-4 pt-6 pb-8">
  <header class="mb-5 flex items-center gap-3">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-sky-700 text-slate-950">
      <Flame size={24} />
    </span>
    <div>
      <h1 class="text-2xl font-bold">Tu Wrapped</h1>
      <p class="text-xs text-slate-500">tus números en bbeat</p>
    </div>
  </header>

  <!-- Selector de rango -->
  <div class="mb-6 inline-flex rounded-lg border border-slate-800 bg-slate-900/60 p-1">
    {#each RANGES as r, i}
      <button
        type="button"
        onclick={() => setRange(i)}
        class="rounded-md px-3 py-1.5 text-xs font-medium transition"
        class:bg-cyan-500={i === rangeIdx}
        class:text-slate-950={i === rangeIdx}
        class:text-slate-400={i !== rangeIdx}
      >{r.label}</button>
    {/each}
  </div>

  {#if error}
    <p class="text-red-400">{error}</p>
  {:else if loading}
    <p class="text-slate-500">Cargando…</p>
  {:else if stats && stats.total_plays === 0}
    <div class="rounded-md border border-dashed border-slate-800 p-8 text-center text-sm text-slate-400">
      No hay reproducciones en este periodo. Prueba otro rango o dale al play 😎
    </div>
  {:else if stats}
    {@const dPlays = stats.prev ? pct(stats.total_plays, stats.prev.plays) : null}
    {@const dMin = stats.prev ? pct(stats.total_minutes, stats.prev.minutes) : null}

    <!-- Hero -->
    <section class="mb-6 grid grid-cols-3 gap-3">
      <div class="rounded-xl border border-cyan-900/40 bg-cyan-950/20 p-4 text-center">
        <Flame size={18} class="mx-auto mb-1 text-cyan-400" />
        <div class="text-2xl font-bold text-cyan-400">{stats.total_plays}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">plays</div>
        {#if dPlays !== null}
          <div class="mt-1 flex items-center justify-center gap-0.5 text-[10px]" class:text-emerald-400={dPlays >= 0} class:text-red-400={dPlays < 0}>
            {#if dPlays >= 0}<TrendingUp size={11} />{:else}<TrendingDown size={11} />{/if}
            {Math.abs(dPlays)}%
          </div>
        {/if}
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-center">
        <Clock size={18} class="mx-auto mb-1 text-slate-400" />
        <div class="text-2xl font-bold">{stats.total_minutes}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">minutos</div>
        {#if dMin !== null}
          <div class="mt-1 flex items-center justify-center gap-0.5 text-[10px]" class:text-emerald-400={dMin >= 0} class:text-red-400={dMin < 0}>
            {#if dMin >= 0}<TrendingUp size={11} />{:else}<TrendingDown size={11} />{/if}
            {Math.abs(dMin)}%
          </div>
        {/if}
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-center">
        <Music2 size={18} class="mx-auto mb-1 text-slate-400" />
        <div class="text-2xl font-bold">{stats.unique_tracks}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">pistas</div>
      </div>
    </section>

    <!-- Racha + primer/último play -->
    <section class="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-orange-900/40 bg-orange-950/10 p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <Flame size={13} class="text-orange-400" /> Racha
        </div>
        <div class="text-xl font-bold text-orange-300">
          {stats.streak_days} {stats.streak_days === 1 ? 'día' : 'días'}
        </div>
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <CalendarClock size={13} /> Primer play
        </div>
        <div class="text-sm font-semibold">{fmtDate(stats.first_play)}</div>
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div class="mb-1 flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <CalendarClock size={13} /> Último play
        </div>
        <div class="text-sm font-semibold">{fmtDate(stats.last_play)}</div>
      </div>
    </section>

    <!-- Reloj de escucha -->
    <section class="mb-8">
      <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
        <Clock size={14} class="text-cyan-400" /> Reloj de escucha
      </h2>
      <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div class="flex h-24 items-end gap-[3px]">
          {#each stats.clock as c, h}
            <div class="group relative flex-1" title="{h}:00 · {c} plays">
              <div
                class="w-full rounded-t bg-cyan-500/70 transition-all group-hover:bg-cyan-400"
                style:height="{Math.max(2, (c / clockMax) * 88)}px"
              ></div>
            </div>
          {/each}
        </div>
        <div class="mt-1.5 flex justify-between text-[9px] text-slate-600">
          <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
        </div>
      </div>
    </section>

    <!-- Tus top tracks -->
    {#if stats.top_tracks.length > 0}
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Trophy size={14} class="text-cyan-400" /> Tus más escuchadas
        </h2>
        <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
          {#each stats.top_tracks as t, i (t.id)}
            <li>
              <button
                onclick={() => stats && player.playTracks(stats.top_tracks, i)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
              >
                <span class="w-5 flex-none text-center font-mono text-xs text-slate-600">{i + 1}</span>
                {#if t.cover_url}
                  <img loading="lazy" decoding="async" src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={14} /></div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-slate-500">{t.artist_name}</div>
                </div>
                <span class="flex-none text-xs text-slate-500">{t.plays}×</span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Tus top artistas -->
    {#if stats.top_artists.length > 0}
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Users size={14} class="text-cyan-400" /> Tus artistas top
        </h2>
        <div class="flex flex-wrap gap-2">
          {#each stats.top_artists as a, i (a.id)}
            <a
              href="/artists/{a.id}"
              class="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm transition hover:border-cyan-700/50"
            >
              <span class="font-mono text-xs text-slate-600">{i + 1}</span>
              {a.name}
              <span class="text-xs text-cyan-400">{a.plays}×</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Tarjeta compartible -->
    <section>
      <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
        <Share2 size={14} class="text-cyan-400" /> Comparte tu wrapped
      </h2>
      <div class="flex flex-col items-center gap-4">
        <div bind:this={cardEl}>
          <WrappedCard {stats} username={auth.user?.username ?? 'bbeat'} {rangeLabel} />
        </div>
        <button
          type="button"
          onclick={share}
          disabled={sharing}
          class="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
        >
          <Share2 size={16} /> {sharing ? 'Generando…' : 'Compartir imagen'}
        </button>
      </div>
    </section>
  {/if}
</div>
