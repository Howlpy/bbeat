<script lang="ts">
  import { coverSrc } from '$lib/cover';
  import { onMount } from 'svelte';
  import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, Music2, ListMusic } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';
  import { formatDuration } from '$lib/api';
  import NowPlaying from './NowPlaying.svelte';
  import Queue from './Queue.svelte';

  let {
    bottom = 0,
    height = $bindable(0)
  }: {
    /** Altura de la navbar: el mini player se apoya justo encima de ella. */
    bottom?: number;
    height?: number;
  } = $props();

  let audioA: HTMLAudioElement;
  let audioB: HTMLAudioElement;
  let volumeOpen = $state(false);
  let volumePanel = $state<HTMLDivElement | null>(null);
  let nowPlayingOpen = $state(false);
  let queueOpen = $state(false);

  onMount(() => {
    // Dos elementos: activo + en espera (precarga de la siguiente pista).
    player.attach(audioA, audioB);
  });

  function onVolume(e: Event) {
    const target = e.target as HTMLInputElement;
    player.setVolume(Number(target.value));
  }

  function onDocClick(e: MouseEvent) {
    if (!volumeOpen) return;
    if (volumePanel && !volumePanel.contains(e.target as Node)) {
      volumeOpen = false;
    }
  }

  $effect(() => {
    if (volumeOpen) {
      document.addEventListener('click', onDocClick, true);
      return () => document.removeEventListener('click', onDocClick, true);
    }
  });

  function openExpanded() {
    nowPlayingOpen = true;
  }
</script>

<audio bind:this={audioA} preload="auto"></audio>
<audio bind:this={audioB} preload="auto"></audio>

{#if player.current}
  <!-- Mini player apoyado justo encima de la navbar -->
  <div
    bind:clientHeight={height}
    class="fixed inset-x-0 z-40 border-t border-line bg-surface"
    style:bottom="{bottom}px"
  >
    <!-- Barra de progreso -->
    <div class="relative h-[3px] bg-surface-3">
      <div
        class="absolute inset-y-0 left-0 bg-accent transition-all duration-300"
        style:width="{player.duration ? (player.position / player.duration) * 100 : 0}%"
      ></div>
    </div>

    <div class="mx-auto flex max-w-5xl items-center gap-2 px-3 py-2 sm:gap-3 sm:px-4">
      <!-- Cover + título + artista: abre NowPlaying -->
      <button
        onclick={openExpanded}
        class="flex min-w-0 flex-1 items-center gap-3 text-left"
        aria-label="Abrir reproductor"
      >
        {#if player.current.cover_url}
          <img loading="lazy" decoding="async"
            src={coverSrc(player.current.cover_url, 96)}
            alt=""
            class="size-12 flex-none rounded-lg object-cover"
          />
        {:else}
          <div class="grid size-12 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle">
            <Music2 size={18} />
          </div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-semibold">{player.current.title}</div>
          <div class="truncate text-xs text-fg-muted">{player.current.artist_name}</div>
        </div>
      </button>

      <!-- Controles -->
      <div class="flex flex-none items-center">
        <button
          aria-label="Anterior"
          onclick={() => player.prev()}
          class="grid size-10 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg"
        ><SkipBack size={18} fill="currentColor" /></button>

        <button
          aria-label={player.isPlaying ? 'Pausar' : 'Reproducir'}
          onclick={() => player.toggle()}
          class="mx-0.5 grid size-11 place-items-center rounded-full bg-accent text-accent-fg hover:bg-accent-hover"
        >
          {#if player.isPlaying}
            <Pause size={18} fill="currentColor" />
          {:else}
            <Play size={18} fill="currentColor" class="ml-0.5" />
          {/if}
        </button>

        <button
          aria-label="Siguiente"
          onclick={() => player.next()}
          class="grid size-10 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg"
        ><SkipForward size={18} fill="currentColor" /></button>

        <!-- Volumen (oculto en móvil: se usan los botones del dispositivo) -->
        <div class="relative hidden sm:block" bind:this={volumePanel}>
          <button
            aria-label="Volumen"
            onclick={(e) => { e.stopPropagation(); volumeOpen = !volumeOpen; }}
            class="grid size-10 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg"
          >
            {#if player.muted || player.volume === 0}
              <VolumeX size={18} />
            {:else}
              <Volume2 size={18} />
            {/if}
          </button>
          {#if volumeOpen}
            <div
              class="absolute bottom-full right-0 mb-2 flex items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-2 shadow-lg"
              role="dialog"
            >
              <button
                onclick={() => player.toggleMute()}
                class="grid size-10 flex-none place-items-center rounded-full hover:bg-surface-3"
                aria-label="Silenciar"
              >
                {#if player.muted}<VolumeX size={16} />{:else}<Volume2 size={16} />{/if}
              </button>
              <input
                type="range" min="0" max="1" step="0.01"
                value={player.volume}
                oninput={onVolume}
                class="seek w-32"
              />
              <span class="w-9 text-right text-xs tabular-nums text-fg-muted">
                {Math.round(player.volume * 100)}
              </span>
            </div>
          {/if}
        </div>

        <button
          aria-label="Cola"
          onclick={() => (queueOpen = true)}
          class="grid size-10 place-items-center rounded-full text-fg-muted hover:bg-surface-2 hover:text-fg"
        ><ListMusic size={18} /></button>
      </div>
    </div>
  </div>
{/if}

{#if nowPlayingOpen}
  <NowPlaying onclose={() => (nowPlayingOpen = false)} onqueue={() => (queueOpen = true)} />
{/if}

{#if queueOpen}
  <Queue onclose={() => (queueOpen = false)} />
{/if}
