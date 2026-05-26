<script lang="ts">
  import { onMount } from 'svelte';
  import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, ChevronUp, Music2, ListMusic } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';
  import { formatDuration } from '$lib/api';
  import NowPlaying from './NowPlaying.svelte';
  import Queue from './Queue.svelte';

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
  <!-- Mini player anclado al bottom -->
  <div class="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-slate-950/95 backdrop-blur">
    <!-- Barra de progreso fina arriba del player -->
    <div class="relative h-0.5 bg-slate-800">
      <div
        class="absolute inset-y-0 left-0 bg-cyan-400 transition-all duration-300"
        style:width="{player.duration ? (player.position / player.duration) * 100 : 0}%"
      ></div>
    </div>

    <div class="mx-auto flex max-w-5xl items-center gap-3 px-3 py-2 sm:gap-4 sm:px-4">
      <!-- Cover + título + artista (clickable) → abre NowPlaying -->
      <button
        onclick={openExpanded}
        class="flex min-w-0 flex-1 items-center gap-3 text-left"
        aria-label="Abrir reproductor"
      >
        {#if player.current.cover_url}
          <img
            src={player.current.cover_url}
            alt=""
            class="size-12 flex-none rounded object-cover sm:size-14"
          />
        {:else}
          <div class="grid size-12 flex-none place-items-center rounded bg-slate-800 text-slate-600 sm:size-14">
            <Music2 size={18} />
          </div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium">{player.current.title}</div>
          <div class="truncate text-xs text-slate-400">{player.current.artist_name}</div>
        </div>
      </button>

      <!-- Controles -->
      <div class="flex flex-none items-center gap-1">
        <button
          aria-label="Anterior"
          onclick={() => player.prev()}
          class="hidden size-9 place-items-center rounded text-slate-300 hover:bg-slate-800 sm:grid"
        ><SkipBack size={18} fill="currentColor" /></button>

        <button
          aria-label={player.isPlaying ? 'Pausar' : 'Reproducir'}
          onclick={() => player.toggle()}
          class="grid size-10 place-items-center rounded-full bg-cyan-400 text-slate-950 hover:bg-cyan-300"
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
          class="grid size-9 place-items-center rounded text-slate-300 hover:bg-slate-800"
        ><SkipForward size={18} fill="currentColor" /></button>

        <!-- Volumen (oculto en móvil para no apretar) -->
        <div class="relative hidden sm:block" bind:this={volumePanel}>
          <button
            aria-label="Volumen"
            onclick={(e) => { e.stopPropagation(); volumeOpen = !volumeOpen; }}
            class="grid size-9 place-items-center rounded text-slate-300 hover:bg-slate-800"
          >
            {#if player.muted || player.volume === 0}
              <VolumeX size={18} />
            {:else}
              <Volume2 size={18} />
            {/if}
          </button>
          {#if volumeOpen}
            <div
              class="absolute bottom-full right-0 mb-2 flex items-center gap-2 rounded border border-slate-800 bg-slate-900 px-3 py-2 shadow-lg"
              role="dialog"
            >
              <button
                onclick={() => player.toggleMute()}
                class="grid size-7 flex-none place-items-center rounded hover:bg-slate-800"
              >
                {#if player.muted}<VolumeX size={14} />{:else}<Volume2 size={14} />{/if}
              </button>
              <input
                type="range" min="0" max="1" step="0.01"
                value={player.volume}
                oninput={onVolume}
                class="h-1 w-32 cursor-pointer appearance-none rounded bg-slate-800 accent-cyan-400"
              />
              <span class="w-9 text-right font-mono text-xs text-slate-400">
                {Math.round(player.volume * 100)}
              </span>
            </div>
          {/if}
        </div>

        <button
          aria-label="Cola"
          onclick={() => (queueOpen = true)}
          class="grid size-9 place-items-center rounded text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        ><ListMusic size={18} /></button>

        <button
          aria-label="Expandir"
          onclick={openExpanded}
          class="grid size-9 place-items-center rounded text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        ><ChevronUp size={18} /></button>
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
