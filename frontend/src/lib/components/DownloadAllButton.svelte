<script lang="ts">
  import { HardDriveDownload, Loader2, CircleCheck } from 'lucide-svelte';
  import { offline } from '$lib/offline.svelte';
  import type { Track } from '$lib/api';

  let {
    tracks,
    label = 'Descargar',
    class: klass = 'rounded-full border border-slate-700 px-4 py-2'
  }: { tracks: Track[]; label?: string; class?: string } = $props();

  const total = $derived(tracks.length);
  const done = $derived(tracks.filter((t) => offline.has(t.id)).length);
  const busy = $derived(tracks.some((t) => offline.downloading.has(t.id)));
  const allDone = $derived(total > 0 && done === total);

  async function downloadAll() {
    // Secuencial: no martilleamos el server ni la RAM con N descargas a la vez.
    for (const t of tracks) {
      if (!offline.has(t.id) && !offline.downloading.has(t.id)) {
        await offline.download(t);
      }
    }
  }
</script>

{#if total > 0}
  <button
    onclick={downloadAll}
    disabled={busy || allDone}
    class="inline-flex items-center gap-2 text-sm transition hover:bg-slate-800 disabled:opacity-60 {klass}"
    title={allDone ? 'Todas descargadas' : 'Descargar todas para escuchar sin conexión'}
  >
    {#if busy}
      <Loader2 size={16} class="animate-spin" /> Descargando {done}/{total}
    {:else if allDone}
      <CircleCheck size={16} class="text-cyan-400" /> Descargado
    {:else}
      <HardDriveDownload size={16} /> {label}{done ? ` (${done}/${total})` : ''}
    {/if}
  </button>
{/if}
