<script lang="ts">
  import { HardDriveDownload, Trash2, Play, Shuffle, WifiOff } from 'lucide-svelte';
  import { offline } from '$lib/offline.svelte';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import type { Track } from '$lib/api';

  let tracks = $state<Track[]>([]);
  // Se reconstruye cuando cambia el set de descargas.
  $effect(() => {
    offline.ids;
    tracks = offline.downloadedTracks();
  });

  function playAll() {
    if (tracks.length) player.playTracks(tracks, 0);
  }
  function shuffleAll() {
    if (tracks.length) player.playShuffled(tracks);
  }
  async function clearAll() {
    if (!confirm('¿Quitar todas las descargas del dispositivo?')) return;
    for (const t of [...tracks]) await offline.remove(t.id);
  }
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <header class="mb-4 flex items-center gap-3">
    <span class="grid size-14 flex-none place-items-center rounded bg-gradient-to-br from-cyan-400 to-sky-700 text-slate-950">
      <HardDriveDownload size={26} />
    </span>
    <div>
      <h1 class="text-2xl font-bold">Descargas</h1>
      <p class="text-xs text-slate-500">
        {tracks.length} {tracks.length === 1 ? 'pista' : 'pistas'} · disponibles sin conexión
      </p>
    </div>
  </header>

  {#if tracks.length > 0}
    <div class="mb-4 flex items-center gap-2">
      <button
        onclick={playAll}
        class="inline-flex items-center gap-2 rounded-full bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
      >
        <Play size={16} fill="currentColor" /> Reproducir
      </button>
      <button
        onclick={shuffleAll}
        class="inline-flex items-center gap-2 rounded-full border border-slate-700 px-4 py-2 text-sm transition hover:bg-slate-800"
      >
        <Shuffle size={16} /> Aleatorio
      </button>
      <button
        onclick={clearAll}
        class="ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-xs text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
      >
        <Trash2 size={14} /> Vaciar
      </button>
    </div>
    <TrackList bind:tracks />
  {:else}
    <div class="rounded-md border border-dashed border-slate-800 p-8 text-center text-sm text-slate-400">
      <WifiOff class="mx-auto mb-2 text-slate-600" size={28} />
      Aún no has descargado nada. Pulsa <b>⋮ → Descargar</b> en cualquier canción para escucharla sin internet.
    </div>
  {/if}
</div>
