<script lang="ts">
  import { fly, fade } from 'svelte/transition';
  import { X, Music2, ListMusic, Trash2, Volume2 } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';

  let { onclose }: { onclose: () => void } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<!-- Backdrop -->
<button
  class="fixed inset-0 z-[60] cursor-default bg-black/60 backdrop-blur-sm"
  onclick={onclose}
  aria-label="Cerrar cola"
  transition:fade={{ duration: 150 }}
></button>

<!-- Bottom sheet -->
<div
  class="fixed inset-x-0 bottom-0 z-[61] mx-auto flex max-h-[78vh] max-w-2xl flex-col rounded-t-2xl border border-b-0 border-slate-700/60 bg-slate-900/95 shadow-2xl shadow-black/50 backdrop-blur-xl"
  transition:fly={{ y: 420, duration: 280 }}
>
  <!-- Tirador -->
  <div class="flex flex-none justify-center pt-2.5">
    <span class="h-1 w-10 rounded-full bg-slate-600"></span>
  </div>

  <header class="flex flex-none items-center justify-between px-4 py-3">
    <h2 class="flex items-center gap-2 text-base font-bold">
      <ListMusic size={18} class="text-cyan-400" /> Cola
      <span class="text-sm font-normal text-slate-500">· {player.queue.length}</span>
    </h2>
    <button
      onclick={onclose}
      class="grid size-8 place-items-center rounded-full text-slate-400 transition hover:bg-slate-800"
      aria-label="Cerrar"
    ><X size={18} /></button>
  </header>

  <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-5">
    {#if player.queue.length === 0}
      <p class="p-8 text-center text-sm text-slate-500">La cola está vacía.</p>
    {:else}
      <ul class="divide-y divide-slate-800/70">
        {#each player.queue as t, i (`${t.id}-${i}`)}
          {@const isCurrent = i === player.index}
          <li class="flex items-center gap-3 rounded-lg px-2 py-2 {isCurrent ? 'bg-slate-800/50' : ''}">
            <button
              onclick={() => player.jumpTo(i)}
              class="flex min-w-0 flex-1 items-center gap-3 text-left"
            >
              {#if isCurrent}
                <span class="grid size-10 flex-none place-items-center rounded bg-cyan-400/15 text-cyan-400">
                  <Volume2 size={16} />
                </span>
              {:else if t.cover_url}
                <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600">
                  <Music2 size={14} />
                </div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm" class:text-cyan-400={isCurrent}>{t.title}</div>
                <div class="truncate text-xs text-slate-500">{t.artist_name}</div>
              </div>
            </button>
            <button
              onclick={() => player.removeFromQueue(i)}
              class="grid size-8 flex-none place-items-center rounded text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
              aria-label="Quitar de la cola"
            ><Trash2 size={15} /></button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>
