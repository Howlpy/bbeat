<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { player } from '$lib/player.svelte';

  let { onclose }: { onclose: () => void } = $props();

  type Line = { time: number; text: string };
  let plain = $state<string | null>(null);
  let synced = $state<Line[] | null>(null);
  let loading = $state(true);
  let notFound = $state(false);
  let error = $state<string | null>(null);
  let trackId = $state<number | null>(null);
  let containerEl = $state<HTMLDivElement | null>(null);

  function parseSyncedLyrics(text: string): Line[] {
    const lines: Line[] = [];
    for (const ln of text.split(/\r?\n/)) {
      // [mm:ss.xx] texto    ó    [mm:ss] texto
      const m = ln.match(/^\[(\d+):(\d+(?:\.\d+)?)\]\s?(.*)$/);
      if (!m) continue;
      const mm = parseInt(m[1], 10);
      const ss = parseFloat(m[2]);
      lines.push({ time: mm * 60 + ss, text: m[3] });
    }
    return lines;
  }

  async function fetchLyrics(id: number) {
    loading = true;
    notFound = false;
    error = null;
    plain = null;
    synced = null;
    try {
      const r = await api.lyrics(id);
      if (!r.found) {
        notFound = true;
      } else {
        plain = r.plain ?? null;
        if (r.synced) synced = parseSyncedLyrics(r.synced);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  // Cuando cambia el track, recargar
  $effect(() => {
    const id = player.current?.id ?? null;
    if (id !== trackId) {
      trackId = id;
      if (id !== null) fetchLyrics(id);
    }
  });

  // Línea actual basada en player.position
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

  // Auto-scroll a la línea activa
  $effect(() => {
    if (!containerEl || currentLineIdx < 0) return;
    const el = containerEl.querySelector<HTMLElement>(`[data-idx="${currentLineIdx}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });
</script>

<div
  class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
  onclick={onclose}
  role="dialog"
  aria-label="Letras"
>
  <div
    class="absolute inset-x-0 bottom-0 top-12 flex flex-col rounded-t-xl border-t border-neutral-800 bg-neutral-950"
    onclick={(e) => e.stopPropagation()}
  >
    <header class="flex flex-none items-center justify-between border-b border-neutral-800 p-3">
      <div class="min-w-0">
        <div class="text-xs text-neutral-500">Letras</div>
        {#if player.current}
          <div class="truncate text-sm font-semibold">{player.current.title}</div>
          <div class="truncate text-xs text-neutral-400">{player.current.artist_name}</div>
        {/if}
      </div>
      <button onclick={onclose} class="rounded p-2 text-neutral-400 hover:bg-neutral-800">✕</button>
    </header>

    <div bind:this={containerEl} class="flex-1 overflow-y-auto px-4 py-6">
      {#if loading}
        <p class="text-center text-sm text-neutral-500">Buscando letras…</p>
      {:else if error}
        <p class="rounded-md border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">⚠️ {error}</p>
      {:else if notFound}
        <p class="text-center text-sm text-neutral-500">
          LRCLIB no tiene letras para esta pista.<br />
          <span class="text-xs text-neutral-600">(prueba con un título limpio sin "Official Video" etc.)</span>
        </p>
      {:else if synced}
        <div class="mx-auto max-w-md space-y-3 py-12 text-center">
          {#each synced as line, i}
            <p
              data-idx={i}
              class="text-base transition-all duration-300"
              class:text-emerald-400={i === currentLineIdx}
              class:text-2xl={i === currentLineIdx}
              class:font-semibold={i === currentLineIdx}
              class:text-neutral-500={i !== currentLineIdx}
            >{line.text || '♪'}</p>
          {/each}
        </div>
      {:else if plain}
        <pre class="mx-auto max-w-md whitespace-pre-wrap text-sm leading-relaxed text-neutral-300">{plain}</pre>
      {/if}
    </div>
  </div>
</div>
