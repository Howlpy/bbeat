<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Play,
    Pause,
    SkipBack,
    SkipForward,
    ChevronDown,
    Shuffle,
    Repeat,
    Repeat1,
    Heart,
    ListMusic,
    Mic2,
    Music2
  } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';
  import { api, formatDuration } from '$lib/api';
  import { dominantColor } from '$lib/visual';

  let { onclose, onqueue }: { onclose: () => void; onqueue: () => void } = $props();

  // Color ambiente extraído de la portada
  let accent = $state<[number, number, number]>([34, 45, 70]);
  $effect(() => {
    const url = player.current?.cover_url;
    if (!url) {
      accent = [34, 45, 70];
      return;
    }
    dominantColor(url)
      .then((c) => (accent = c))
      .catch(() => {});
  });

  let plain = $state<string | null>(null);
  let synced = $state<{ time: number; text: string }[] | null>(null);
  let lyricsLoading = $state(true);
  let lyricsTrackId = $state<number | null>(null);
  let activeTab = $state<'cover' | 'lyrics'>('cover');
  let lyricsContainer = $state<HTMLDivElement | null>(null);

  function parseSyncedLyrics(text: string): { time: number; text: string }[] {
    const out: { time: number; text: string }[] = [];
    for (const ln of text.split(/\r?\n/)) {
      const m = ln.match(/^\[(\d+):(\d+(?:\.\d+)?)\]\s?(.*)$/);
      if (!m) continue;
      out.push({ time: parseInt(m[1], 10) * 60 + parseFloat(m[2]), text: m[3] });
    }
    return out;
  }

  $effect(() => {
    const id = player.current?.id ?? null;
    if (id !== lyricsTrackId) {
      lyricsTrackId = id;
      plain = null;
      synced = null;
      if (id !== null) {
        lyricsLoading = true;
        api
          .lyrics(id)
          .then((r) => {
            if (r.found) {
              plain = r.plain ?? null;
              if (r.synced) synced = parseSyncedLyrics(r.synced);
            }
          })
          .catch(() => {})
          .finally(() => (lyricsLoading = false));
      }
    }
  });

  const currentLineIdx = $derived.by(() => {
    if (!synced) return -1;
    const t = player.position;
    let idx = -1;
    for (let i = 0; i < synced.length; i++) {
      if (synced[i].time <= t) idx = i;
      else break;
    }
    return idx;
  });

  $effect(() => {
    if (!lyricsContainer || currentLineIdx < 0 || activeTab !== 'lyrics') return;
    const el = lyricsContainer.querySelector<HTMLElement>(`[data-idx="${currentLineIdx}"]`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });

  function onSeek(e: Event) {
    const target = e.target as HTMLInputElement;
    player.seek(Number(target.value));
  }

  // Cerrar con swipe down
  let touchStart = $state(0);
  let touchDelta = $state(0);

  function onTouchStart(e: TouchEvent) {
    touchStart = e.touches[0].clientY;
    touchDelta = 0;
  }
  function onTouchMove(e: TouchEvent) {
    touchDelta = e.touches[0].clientY - touchStart;
  }
  function onTouchEnd() {
    if (touchDelta > 120) onclose();
    touchDelta = 0;
  }
</script>

{#if player.current}
  <div
    class="fixed inset-0 z-50 flex flex-col bg-black"
    style:transform="translateY({touchDelta > 0 ? touchDelta : 0}px)"
    style:transition={touchDelta === 0 ? 'transform 0.2s' : 'none'}
    ontouchstart={onTouchStart}
    ontouchmove={onTouchMove}
    ontouchend={onTouchEnd}
  >
    <!-- Fondo ambiente del color de la portada -->
    <div
      class="pointer-events-none absolute inset-0 -z-10"
      style:background="radial-gradient(ellipse 95% 55% at 50% 0%, rgba({accent[0]},{accent[1]},{accent[2]},0.6), transparent 72%), linear-gradient(180deg, rgb(2 6 23), #000 75%)"
      style:transition="background 700ms ease"
    ></div>
    <!-- Header -->
    <header class="flex flex-none items-center justify-between p-4">
      <button
        onclick={onclose}
        class="grid size-10 place-items-center rounded-full text-slate-300 hover:bg-slate-800"
        aria-label="Cerrar"
      >
        <ChevronDown size={24} />
      </button>
      <div class="min-w-0 text-center">
        <div class="text-xs uppercase tracking-widest text-slate-500">Reproduciendo</div>
        <div class="truncate text-sm font-medium">
          {player.current.album_title || 'Sin álbum'}
        </div>
      </div>
      <div class="flex flex-none items-center gap-1">
        <button
          onclick={() => player.toggleLikeCurrent()}
          class="grid size-10 place-items-center rounded-full transition hover:bg-slate-800"
          class:text-cyan-400={player.current.liked}
          class:text-slate-300={!player.current.liked}
          aria-label={player.current.liked ? 'Quitar de me gusta' : 'Me gusta'}
        ><Heart size={20} fill={player.current.liked ? 'currentColor' : 'none'} /></button>
        <button
          onclick={onqueue}
          class="grid size-10 place-items-center rounded-full text-slate-300 transition hover:bg-slate-800"
          aria-label="Ver cola"
        ><ListMusic size={20} /></button>
      </div>
    </header>

    <!-- Tabs -->
    <div class="flex flex-none justify-center gap-1 px-4">
      <button
        onclick={() => (activeTab = 'cover')}
        class="px-4 py-1.5 text-xs uppercase tracking-wider"
        class:text-cyan-400={activeTab === 'cover'}
        class:text-slate-500={activeTab !== 'cover'}
      >Portada</button>
      <button
        onclick={() => (activeTab = 'lyrics')}
        class="flex items-center gap-1 px-4 py-1.5 text-xs uppercase tracking-wider"
        class:text-cyan-400={activeTab === 'lyrics'}
        class:text-slate-500={activeTab !== 'lyrics'}
      >
        <Mic2 size={12} />
        Letras
      </button>
    </div>

    <!-- Contenido -->
    <div class="flex flex-1 flex-col items-center justify-center overflow-hidden px-6 py-4">
      {#if activeTab === 'cover'}
        <div class="relative aspect-square w-full max-w-md">
          {#if player.current.cover_url}
            <img
              src={player.current.cover_url}
              alt=""
              class="size-full rounded-lg object-cover"
              style:box-shadow="0 25px 70px -15px rgba({accent[0]},{accent[1]},{accent[2]},0.6)"
              style:transition="box-shadow 700ms ease"
            />
          {:else}
            <div class="grid size-full place-items-center rounded bg-slate-800 text-slate-700">
              <Music2 size={96} />
            </div>
          {/if}
        </div>
      {:else}
        <div bind:this={lyricsContainer} class="w-full max-w-md flex-1 overflow-y-auto py-6 text-center">
          {#if lyricsLoading}
            <p class="text-sm text-slate-500">Cargando letras…</p>
          {:else if synced}
            <div class="space-y-3 py-12">
              {#each synced as line, i}
                <p
                  data-idx={i}
                  class="text-lg leading-snug transition-all duration-300"
                  class:text-cyan-400={i === currentLineIdx}
                  class:scale-105={i === currentLineIdx}
                  class:font-bold={i === currentLineIdx}
                  class:text-slate-500={i !== currentLineIdx && Math.abs(i - currentLineIdx) > 2}
                  class:text-slate-300={i !== currentLineIdx && Math.abs(i - currentLineIdx) <= 2}
                >{line.text || '...'}</p>
              {/each}
            </div>
          {:else if plain}
            <pre class="whitespace-pre-wrap text-left text-sm leading-relaxed text-slate-300">{plain}</pre>
          {:else}
            <p class="text-sm text-slate-500">No hay letras disponibles para esta pista.</p>
            <p class="mt-2 text-xs text-slate-600">LRCLIB no la tiene catalogada todavía.</p>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Info + controles -->
    <div class="flex-none px-6 pb-8">
      <div class="mb-4 text-center">
        <h2 class="truncate text-2xl font-bold">{player.current.title}</h2>
        <p class="truncate text-base text-slate-400">{player.current.artist_name}</p>
      </div>

      <!-- Scrubber -->
      <div class="mb-4 flex items-center gap-3 text-xs">
        <span class="w-10 text-right font-mono text-slate-400">
          {formatDuration(player.position * 1000)}
        </span>
        <input
          type="range"
          min="0"
          max={player.duration || 0}
          step="0.1"
          value={player.position}
          oninput={onSeek}
          class="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-slate-800 accent-cyan-400"
          aria-label="Posición"
        />
        <span class="w-10 font-mono text-slate-400">
          {formatDuration((player.duration || 0) * 1000)}
        </span>
      </div>

      <!-- Controles -->
      <div class="flex items-center justify-center gap-6">
        <button
          onclick={() => player.toggleShuffle()}
          class="transition"
          class:text-cyan-400={player.shuffle}
          class:text-slate-400={!player.shuffle}
          aria-label="Aleatorio"
        >
          <Shuffle size={22} />
        </button>

        <button
          onclick={() => player.prev()}
          class="text-slate-200 hover:text-white"
          aria-label="Anterior"
        >
          <SkipBack size={32} fill="currentColor" />
        </button>

        <button
          onclick={() => player.toggle()}
          class="grid size-16 place-items-center rounded-full bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/40 transition hover:bg-cyan-300"
          aria-label={player.isPlaying ? 'Pausar' : 'Reproducir'}
        >
          {#if player.isPlaying}
            <Pause size={28} fill="currentColor" />
          {:else}
            <Play size={28} fill="currentColor" class="ml-1" />
          {/if}
        </button>

        <button
          onclick={() => player.next()}
          class="text-slate-200 hover:text-white"
          aria-label="Siguiente"
        >
          <SkipForward size={32} fill="currentColor" />
        </button>

        <button
          onclick={() => player.cycleRepeat()}
          class="transition"
          class:text-cyan-400={player.repeat !== 'off'}
          class:text-slate-400={player.repeat === 'off'}
          aria-label="Repetir"
        >
          {#if player.repeat === 'one'}
            <Repeat1 size={22} />
          {:else}
            <Repeat size={22} />
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}
