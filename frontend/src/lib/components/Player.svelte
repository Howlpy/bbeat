<script lang="ts">
  import { onMount } from 'svelte';
  import { player } from '$lib/player.svelte';
  import { formatDuration } from '$lib/api';

  let audioEl: HTMLAudioElement;

  onMount(() => {
    player.attach(audioEl);
  });

  function onSeek(e: Event) {
    const target = e.target as HTMLInputElement;
    player.seek(Number(target.value));
  }
</script>

<audio bind:this={audioEl} preload="metadata"></audio>

{#if player.current}
  <div class="fixed inset-x-0 bottom-0 z-40 border-t border-neutral-800 bg-neutral-950/95 backdrop-blur">
    <div class="mx-auto flex max-w-5xl items-center gap-3 px-3 py-2 sm:gap-4 sm:px-4 sm:py-3">
      {#if player.current.cover_url}
        <img
          src={player.current.cover_url}
          alt=""
          class="size-12 flex-none rounded object-cover sm:size-14"
        />
      {:else}
        <div class="size-12 flex-none rounded bg-neutral-800 sm:size-14"></div>
      {/if}

      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-medium">{player.current.title}</div>
        <div class="truncate text-xs text-neutral-400">{player.current.artist_name}</div>
        <div class="mt-1 flex items-center gap-2">
          <span class="w-9 text-right font-mono text-[10px] text-neutral-500">
            {formatDuration(player.position * 1000)}
          </span>
          <input
            type="range"
            min="0"
            max={player.duration || 0}
            step="0.1"
            value={player.position}
            oninput={onSeek}
            class="h-1 flex-1 cursor-pointer appearance-none rounded bg-neutral-800 accent-emerald-400"
          />
          <span class="w-9 font-mono text-[10px] text-neutral-500">
            {formatDuration((player.duration || 0) * 1000)}
          </span>
        </div>
      </div>

      <div class="flex flex-none items-center gap-1">
        <button
          aria-label="Anterior"
          onclick={() => player.prev()}
          class="grid size-9 place-items-center rounded text-neutral-300 hover:bg-neutral-800"
        >⏮</button>
        <button
          aria-label={player.isPlaying ? 'Pausar' : 'Reproducir'}
          onclick={() => player.toggle()}
          class="grid size-10 place-items-center rounded-full bg-emerald-500 text-neutral-950 hover:bg-emerald-400"
        >
          {player.isPlaying ? '⏸' : '▶'}
        </button>
        <button
          aria-label="Siguiente"
          onclick={() => player.next()}
          class="grid size-9 place-items-center rounded text-neutral-300 hover:bg-neutral-800"
        >⏭</button>
      </div>
    </div>
  </div>
{/if}
