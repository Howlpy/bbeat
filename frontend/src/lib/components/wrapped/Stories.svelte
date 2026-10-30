<script lang="ts">
  import { onMount } from 'svelte';
  import { Music2, Share2, RotateCcw, X } from 'lucide-svelte';
  import type { Wrapped } from '$lib/api';
  import { coverSrc } from '$lib/cover';
  import { pushBack } from '$lib/backstack.svelte';
  import CountUp from './CountUp.svelte';
  import { renderSummary, sharePng } from './shareImage';
  import {
    COLORS,
    INK,
    PAPER,
    buildSlides,
    fmtNum,
    periodTitle,
    persona,
    topWeekday,
    type SlideKind
  } from './model';

  let { w, username, onclose }: { w: Wrapped; username: string; onclose: () => void } = $props();

  const DURATION = 6000;
  const slides = $derived(buildSlides(w));
  let idx = $state(0);
  let held = $state(false);
  let reduce = $state(false);
  let sharing = $state(false);
  let toast = $state<string | null>(null);
  const kind = $derived<SlideKind>(slides[idx]);
  const last = $derived(idx === slides.length - 1);

  const THEME: Record<SlideKind, { bg: string; fg: string }> = {
    intro: { bg: COLORS.teal, fg: INK },
    minutes: { bg: COLORS.sand, fg: INK },
    song: { bg: COLORS.coral, fg: INK },
    songs: { bg: INK, fg: PAPER },
    artist: { bg: COLORS.lilac, fg: INK },
    genre: { bg: COLORS.mint, fg: INK },
    time: { bg: COLORS.sky, fg: INK },
    facts: { bg: PAPER, fg: INK },
    summary: { bg: COLORS.teal, fg: INK }
  };

  const per = $derived(periodTitle(w.period));
  // 'del mes' / 'de la semana': la preposición concuerda con el periodo.
  const ofPer = $derived(
    ({ week: 'de la semana', month: 'del mes', year: 'del año', all: 'de siempre' } as Record<string, string>)[w.period] ?? ''
  );
  const hours = $derived(w.total_minutes / 60);
  const pers = $derived(persona(w.hours));
  const hoursMax = $derived(Math.max(1, ...w.hours));
  const song = $derived(w.top_tracks[0]);
  const artist = $derived(w.top_artists[0]);

  function next() {
    if (idx < slides.length - 1) idx++;
  }
  function prev() {
    if (idx > 0) idx--;
  }

  // Gestos: toque corto = lado derecho avanza / izquierdo retrocede; mantener = pausa;
  // deslizar = navegar; deslizar hacia abajo = cerrar.
  let down: { x: number; y: number; t: number } | null = null;
  function onDown(e: PointerEvent) {
    if ((e.target as Element).closest('[data-ui]')) return;
    down = { x: e.clientX, y: e.clientY, t: Date.now() };
    held = true;
  }
  function onUp(e: PointerEvent) {
    held = false;
    if (!down) return;
    const dx = e.clientX - down.x;
    const dy = e.clientY - down.y;
    const dt = Date.now() - down.t;
    down = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) return dx < 0 ? next() : prev();
    if (dy > 120 && Math.abs(dy) > Math.abs(dx)) return onclose();
    if (dt > 280 || Math.abs(dx) > 20 || Math.abs(dy) > 20) return;
    const width = (e.currentTarget as HTMLElement).clientWidth;
    if (e.clientX < width * 0.33) prev();
    else next();
  }
  function onCancel() {
    held = false;
    down = null;
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowRight') next();
    else if (e.key === 'ArrowLeft') prev();
    else if (e.key === 'Escape') onclose();
  }

  async function share() {
    sharing = true;
    try {
      const blob = await renderSummary({ w, username });
      const r = await sharePng(blob);
      if (r === 'downloaded') flash('Imagen descargada');
    } catch {
      flash('No se pudo compartir');
    } finally {
      sharing = false;
    }
  }
  function flash(m: string) {
    toast = m;
    setTimeout(() => (toast = null), 2400);
  }

  onMount(() => {
    reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Atrás de Android cierra las stories.
    const off = pushBack(onclose);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      off();
      document.body.style.overflow = prevOverflow;
    };
  });
</script>

<svelte:window onkeydown={onKey} />

{#snippet cover(url: string | null, cls: string, size = 600)}
  {#if url}
    <img src={coverSrc(url, size)} alt="" class="{cls} object-cover" decoding="async" />
  {:else}
    <div class="{cls} grid place-items-center" style:background={INK} style:color={COLORS.teal}>
      <Music2 size={40} />
    </div>
  {/if}
{/snippet}

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="fixed inset-0 z-[200] select-none overflow-hidden"
  style:background={THEME[kind].bg}
  style:color={THEME[kind].fg}
  style:touch-action="none"
  onpointerdown={onDown}
  onpointerup={onUp}
  onpointercancel={onCancel}
  oncontextmenu={(e) => e.preventDefault()}
>
  <!-- Progreso -->
  <div class="absolute inset-x-0 top-0 z-10 flex gap-1.5 px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
    {#each slides as _, i}
      <div class="h-1 flex-1 overflow-hidden rounded-full" style:background="color-mix(in srgb, currentColor 25%, transparent)">
        <div
          class="h-full rounded-full"
          class:seg-run={i === idx && !reduce && !last}
          class:seg-full={i < idx || (i === idx && (reduce || last))}
          style:background="currentColor"
          style:animation-play-state={held ? 'paused' : 'running'}
          onanimationend={() => i === idx && next()}
        ></div>
      </div>
    {/each}
  </div>

  <button
    type="button"
    data-ui
    onclick={onclose}
    class="absolute right-2 top-[max(1.5rem,calc(env(safe-area-inset-top)+0.75rem))] z-10 grid size-11 place-items-center rounded-full"
    aria-label="Cerrar"
  >
    <X size={24} />
  </button>

  {#key idx}
    <div class="absolute inset-0 flex flex-col px-7 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(5.5rem,calc(env(safe-area-inset-top)+4.5rem))]">
      {#if kind === 'intro'}
        <div class="grid w-full max-w-sm grid-cols-3 gap-3 self-center">
          {#each w.top_tracks.slice(0, 5) as t, i (t.id)}
            <div class="pop {i === 0 ? 'col-span-2 row-span-2' : ''}" style:--d="{i * 90}ms">
              {@render cover(t.cover_url, 'aspect-square w-full rounded-2xl', 400)}
            </div>
          {/each}
        </div>
        <div class="mt-auto">
          <p class="rise text-lg font-bold opacity-70" style:--d="500ms">bbeat wrapped</p>
          <h1 class="rise text-[clamp(3.2rem,15vw,5.5rem)] font-extrabold leading-[0.95] tracking-tight" style:--d="600ms">
            Tu {per}<br />en bbeat
          </h1>
          <p class="rise mt-4 text-base font-semibold opacity-70" style:--d="800ms">Toca para continuar</p>
        </div>
      {:else if kind === 'minutes'}
        <p class="rise text-2xl font-bold">Has escuchado</p>
        <div class="my-auto">
          <div class="text-[clamp(4.5rem,27vw,9.5rem)] font-extrabold leading-none tracking-tighter">
            <CountUp value={w.total_minutes} />
          </div>
          <p class="rise text-3xl font-extrabold" style:--d="300ms">minutos de música</p>
          {#if hours >= 2}
            <p class="rise mt-3 text-lg font-semibold opacity-75" style:--d="500ms">
              {hours >= 48 ? `Son ${Math.round((hours / 24) * 10) / 10} días sin parar` : `Casi ${Math.round(hours)} horas`} · {fmtNum(w.total_plays)} plays
            </p>
          {/if}
        </div>
        {#if w.rank_pct}
          <div class="rise rounded-2xl p-5" style:background={INK} style:color={COLORS.sand} style:--d="700ms">
            <p class="text-4xl font-extrabold">{w.rank_pct}%</p>
            <p class="text-base font-semibold" style:color={PAPER}>de los oyentes del servidor escuchan menos que tú</p>
          </div>
        {/if}
      {:else if kind === 'song' && song}
        <p class="rise text-2xl font-bold">Tu canción {ofPer}</p>
        <div class="my-auto">
          <div class="pop mx-auto w-[min(78vw,42vh)]" style:--d="150ms">
            {@render cover(song.cover_url, 'aspect-square w-full rounded-3xl', 800)}
          </div>
          <h2 class="rise mt-7 text-[clamp(2rem,9vw,3.2rem)] font-extrabold leading-tight tracking-tight [overflow-wrap:anywhere]" style:--d="400ms">{song.title}</h2>
          <p class="rise text-xl font-bold opacity-75" style:--d="500ms">{song.artist_name}</p>
        </div>
        <p class="rise text-3xl font-extrabold" style:--d="650ms">{fmtNum(song.plays)} {song.plays === 1 ? 'play' : 'plays'}</p>
      {:else if kind === 'songs'}
        <p class="rise text-2xl font-bold">Tus 5 más escuchadas</p>
        <ol class="my-auto space-y-3">
          {#each w.top_tracks as t, i (t.id)}
            <li class="rise flex items-center gap-4" style:--d="{i * 110}ms">
              <span class="w-8 flex-none text-4xl font-extrabold tabular-nums" style:color={COLORS.teal}>{i + 1}</span>
              {@render cover(t.cover_url, 'size-16 flex-none rounded-xl', 200)}
              <div class="min-w-0 flex-1">
                <p class="truncate text-lg font-bold">{t.title}</p>
                <p class="truncate text-sm opacity-70">{t.artist_name}</p>
              </div>
              <span class="flex-none text-sm font-bold opacity-70">{t.plays}×</span>
            </li>
          {/each}
        </ol>
      {:else if kind === 'artist' && artist}
        <p class="rise text-2xl font-bold">Tu artista {ofPer}</p>
        <div class="my-auto">
          <h2 class="rise text-[clamp(3rem,15vw,5.5rem)] font-extrabold leading-[0.95] tracking-tight [overflow-wrap:anywhere]" style:--d="200ms">{artist.name}</h2>
          <p class="rise mt-3 text-2xl font-bold" style:--d="400ms">{fmtNum(artist.plays)} plays</p>
        </div>
        {#if w.top_artists.length > 1}
          <ol class="space-y-2">
            {#each w.top_artists.slice(1) as a, i (a.id)}
              <li class="rise flex items-baseline gap-3 rounded-xl px-4 py-3" style:background={INK} style:color={PAPER} style:--d="{600 + i * 90}ms">
                <span class="w-5 text-sm font-extrabold" style:color={COLORS.lilac}>{i + 2}</span>
                <span class="min-w-0 flex-1 truncate text-lg font-bold">{a.name}</span>
                <span class="text-sm opacity-70">{a.plays}×</span>
              </li>
            {/each}
          </ol>
        {/if}
      {:else if kind === 'genre' && w.genres.length}
        <p class="rise text-2xl font-bold">Tu género</p>
        <div class="my-auto">
          <h2 class="rise text-[clamp(3rem,14vw,5rem)] font-extrabold leading-[0.95] tracking-tight [overflow-wrap:anywhere]" style:--d="150ms">{w.genres[0].name}</h2>
          <p class="rise mt-2 text-xl font-bold opacity-75" style:--d="300ms">{w.genres[0].pct}% de lo que escuchas</p>
          <div class="mt-9 space-y-4">
            {#each w.genres as g, i (g.genre)}
              <div class="rise" style:--d="{400 + i * 90}ms">
                <div class="mb-1 flex justify-between text-base font-bold">
                  <span class="truncate">{g.name}</span><span>{g.pct}%</span>
                </div>
                <div class="h-3 overflow-hidden rounded-full" style:background="color-mix(in srgb, {INK} 18%, transparent)">
                  <div class="bar h-full rounded-full" style:background={INK} style:width="{Math.max(3, g.pct)}%" style:--d="{500 + i * 90}ms"></div>
                </div>
              </div>
            {/each}
          </div>
        </div>
      {:else if kind === 'time'}
        <p class="rise text-2xl font-bold">Cuándo escuchas</p>
        <div class="my-auto">
          <h2 class="rise text-[clamp(2.8rem,13vw,4.8rem)] font-extrabold leading-[0.98] tracking-tight" style:--d="150ms">{pers.title}</h2>
          <p class="rise mt-3 text-lg font-semibold opacity-80" style:--d="300ms">{pers.text}</p>
          <div class="mt-9 flex h-32 items-end gap-[3px]">
            {#each w.hours as c, h}
              <div
                class="vbar flex-1 rounded-t"
                style:height="{Math.max(4, (c / hoursMax) * 100)}%"
                style:background={INK}
                style:opacity={h === pers.peak ? 1 : 0.3}
                style:--d="{300 + h * 20}ms"
              ></div>
            {/each}
          </div>
          <div class="mt-1 flex justify-between text-xs font-bold opacity-70"><span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span></div>
        </div>
        <div class="rise flex gap-3" style:--d="800ms">
          <div class="flex-1 rounded-2xl p-4" style:background={INK} style:color={PAPER}>
            <p class="text-xs font-bold uppercase opacity-70">Tu hora</p>
            <p class="text-3xl font-extrabold" style:color={COLORS.sky}>{String(pers.peak).padStart(2, '0')}:00</p>
          </div>
          <div class="flex-1 rounded-2xl p-4" style:background={INK} style:color={PAPER}>
            <p class="text-xs font-bold uppercase opacity-70">Tu día</p>
            <p class="text-3xl font-extrabold capitalize" style:color={COLORS.sky}>{topWeekday(w.weekdays)}</p>
          </div>
        </div>
      {:else if kind === 'facts'}
        <p class="rise text-2xl font-bold">Y además…</p>
        <div class="my-auto space-y-6">
          {#if w.best_streak >= 2}
            <div class="rise" style:--d="150ms">
              <p class="text-[clamp(3.5rem,20vw,6rem)] font-extrabold leading-none tracking-tighter" style:color={COLORS.coral}>{w.best_streak}</p>
              <p class="text-xl font-bold">días seguidos escuchando</p>
            </div>
          {/if}
          {#if w.new_tracks > 0 && w.period !== 'all'}
            <div class="rise" style:--d="350ms">
              <p class="text-[clamp(3.5rem,20vw,6rem)] font-extrabold leading-none tracking-tighter" style:color={COLORS.sky}>{fmtNum(w.new_tracks)}</p>
              <p class="text-xl font-bold">canciones nuevas descubiertas{w.new_artists ? ` · ${fmtNum(w.new_artists)} artistas` : ''}</p>
            </div>
          {:else}
            <div class="rise" style:--d="350ms">
              <p class="text-[clamp(3.5rem,20vw,6rem)] font-extrabold leading-none tracking-tighter" style:color={COLORS.sky}>{fmtNum(w.unique_tracks)}</p>
              <p class="text-xl font-bold">canciones distintas · {fmtNum(w.unique_artists)} artistas</p>
            </div>
          {/if}
          <div class="rise" style:--d="550ms">
            <p class="text-[clamp(3.5rem,20vw,6rem)] font-extrabold leading-none tracking-tighter" style:color={COLORS.mint}>{w.active_days}</p>
            <p class="text-xl font-bold">{w.active_days === 1 ? 'día' : 'días'} con música</p>
          </div>
        </div>
      {:else}
        <p class="rise text-2xl font-bold">Tu {per} en bbeat</p>
        <div class="my-auto space-y-3">
          <div class="rise flex items-center gap-4" style:--d="100ms">
            {#if song}{@render cover(song.cover_url, 'size-24 flex-none rounded-2xl', 300)}{/if}
            <div class="min-w-0">
              <p class="text-xs font-bold uppercase opacity-70">Canción top</p>
              <p class="line-clamp-2 text-2xl font-extrabold leading-tight">{song?.title ?? '—'}</p>
              <p class="truncate text-sm font-semibold opacity-75">{song?.artist_name ?? ''}</p>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="rise rounded-2xl p-4" style:background={INK} style:color={PAPER} style:--d="250ms">
              <p class="text-xs font-bold uppercase opacity-70">Artista top</p>
              <p class="truncate text-xl font-extrabold" style:color={COLORS.teal}>{artist?.name ?? '—'}</p>
            </div>
            <div class="rise rounded-2xl p-4" style:background={INK} style:color={PAPER} style:--d="350ms">
              <p class="text-xs font-bold uppercase opacity-70">Género top</p>
              <p class="truncate text-xl font-extrabold" style:color={COLORS.teal}>{w.genres[0]?.name ?? '—'}</p>
            </div>
          </div>
          <div class="rise pt-3" style:--d="450ms">
            <p class="text-xs font-bold uppercase opacity-70">Minutos escuchados</p>
            <p class="text-[clamp(4rem,22vw,7rem)] font-extrabold leading-none tracking-tighter">{fmtNum(w.total_minutes)}</p>
          </div>
        </div>
        <div class="flex gap-3" data-ui>
          <button
            type="button"
            data-ui
            onclick={share}
            disabled={sharing}
            class="flex min-h-14 flex-1 items-center justify-center gap-2 rounded-2xl text-lg font-extrabold disabled:opacity-60"
            style:background={INK}
            style:color={COLORS.teal}
          >
            <Share2 size={20} /> {sharing ? 'Generando…' : 'Compartir'}
          </button>
          <button
            type="button"
            data-ui
            onclick={() => (idx = 0)}
            class="grid size-14 place-items-center rounded-2xl border-[3px]"
            style:border-color={INK}
            aria-label="Ver otra vez"
          >
            <RotateCcw size={20} />
          </button>
        </div>
      {/if}
    </div>
  {/key}

  {#if toast}
    <div class="absolute inset-x-0 bottom-28 z-10 mx-auto w-fit rounded-full px-4 py-2 text-sm font-bold" style:background={INK} style:color={PAPER}>{toast}</div>
  {/if}
</div>

<style>
  .seg-full {
    width: 100%;
  }
  .seg-run {
    animation: fill 6000ms linear forwards;
  }
  @keyframes fill {
    from {
      width: 0;
    }
    to {
      width: 100%;
    }
  }
  .rise {
    animation: rise 600ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
    animation-delay: var(--d, 0ms);
  }
  .pop {
    animation: pop 600ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
    animation-delay: var(--d, 0ms);
  }
  .bar {
    transform-origin: left bottom;
    animation: grow 700ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
    animation-delay: var(--d, 0ms);
  }
  .vbar {
    transform-origin: center bottom;
    animation: growy 700ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
    animation-delay: var(--d, 0ms);
  }
  @keyframes growy {
    from {
      transform: scale(1, 0);
    }
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(24px);
    }
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: scale(0.9);
    }
  }
  @keyframes grow {
    from {
      transform: scale(0, 1);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .rise,
    .pop,
    .vbar,
    .bar {
      animation: none;
    }
  }
</style>
