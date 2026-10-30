<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import { HardDriveDownload, Trash2, Play, Shuffle, WifiOff } from 'lucide-svelte';
  import { offline } from '$lib/offline.svelte';
  import { player } from '$lib/player.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
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

<div class="page-narrow">
  <BackButton fallback="/library" />
  <header class="mb-6 flex items-center gap-4">
    <span class="grid size-14 flex-none place-items-center rounded-xl bg-accent-soft text-accent">
      <HardDriveDownload size={26} />
    </span>
    <div>
      <h1 class="page-title">Descargas</h1>
      <p class="text-sm text-fg-muted">
        {tracks.length} {tracks.length === 1 ? 'pista' : 'pistas'} · disponibles sin conexión
      </p>
    </div>
  </header>

  {#if tracks.length > 0}
    <div class="mb-4 flex flex-wrap items-center gap-2">
      <Button variant="primary" onclick={playAll}><Play size={16} fill="currentColor" /> Reproducir</Button>
      <Button onclick={shuffleAll}><Shuffle size={16} /> Aleatorio</Button>
      <Button variant="ghost" onclick={clearAll} class="ml-auto hover:!text-danger"><Trash2 size={16} /> Vaciar</Button>
    </div>
    <TrackList bind:tracks />
  {:else}
    <EmptyState icon={WifiOff} title="Aún no has guardado nada offline" text="Pulsa ⋮ → Descargar en cualquier canción para escucharla sin internet." />
  {/if}
</div>
