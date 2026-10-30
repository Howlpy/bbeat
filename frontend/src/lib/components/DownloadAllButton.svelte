<script lang="ts">
  import { HardDriveDownload, Loader2, CircleCheck } from 'lucide-svelte';
  import { offline } from '$lib/offline.svelte';
  import type { Track } from '$lib/api';

  let {
    tracks,
    label = 'Guardar offline',
    class: klass = 'min-h-11 rounded-lg border border-line-strong bg-surface-2 px-4 sm:min-h-10'
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
    class="inline-flex items-center gap-2 text-left text-sm font-medium transition hover:bg-surface-2 disabled:opacity-60 {klass}"
    title={allDone ? 'Todas guardadas offline' : 'Guardar todas para escuchar sin conexión'}
  >
    {#if busy}
      <Loader2 size={16} class="animate-spin" /> Guardando {done}/{total}
    {:else if allDone}
      <CircleCheck size={16} class="text-accent" /> Guardado offline
    {:else}
      <HardDriveDownload size={16} /> {label}{done ? ` (${done}/${total})` : ''}
    {/if}
  </button>
{/if}
