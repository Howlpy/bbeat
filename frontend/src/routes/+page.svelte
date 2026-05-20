<script lang="ts">
  import { onMount } from 'svelte';
  import { api, formatBytes, type LibraryStats } from '$lib/api';

  let stats = $state<LibraryStats | null>(null);
  let error = $state<string | null>(null);
  let scanning = $state(false);

  async function load() {
    try {
      stats = await api.stats();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function rescan() {
    scanning = true;
    try {
      await api.startScan();
      // poll until done
      let s = await api.scanStatus();
      while (s.running) {
        await new Promise((r) => setTimeout(r, 700));
        s = await api.scanStatus();
      }
      await load();
    } finally {
      scanning = false;
    }
  }

  onMount(load);
</script>

<div class="mx-auto max-w-2xl px-4 pt-6 sm:pt-10">
  <header class="mb-8 flex items-baseline gap-2">
    <h1 class="text-3xl font-bold tracking-tight">
      <span class="text-emerald-400">B</span>beat
    </h1>
    <span class="text-xs text-neutral-500">tu música, en tu red</span>
  </header>

  {#if error}
    <p class="rounded-md border border-red-900/50 bg-red-950/50 p-3 text-sm text-red-300">
      ⚠️ {error}
    </p>
  {:else if !stats}
    <p class="text-neutral-500">Cargando…</p>
  {:else}
    <section class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <a href="/library" class="rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700">
        <div class="text-3xl font-bold text-emerald-400">{stats.tracks}</div>
        <div class="text-xs text-neutral-500">canciones</div>
      </a>
      <a href="/albums" class="rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700">
        <div class="text-3xl font-bold">{stats.albums}</div>
        <div class="text-xs text-neutral-500">álbumes</div>
      </a>
      <a href="/artists" class="rounded-lg border border-neutral-800 bg-neutral-900 p-4 hover:border-neutral-700">
        <div class="text-3xl font-bold">{stats.artists}</div>
        <div class="text-xs text-neutral-500">artistas</div>
      </a>
      <div class="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
        <div class="text-3xl font-bold">{formatBytes(stats.total_bytes)}</div>
        <div class="text-xs text-neutral-500">en disco</div>
      </div>
    </section>

    <div class="mt-6 flex flex-wrap gap-2">
      <button
        onclick={rescan}
        disabled={scanning}
        class="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-emerald-400 disabled:opacity-50"
      >
        {scanning ? 'Escaneando…' : 'Re-escanear biblioteca'}
      </button>
      <a
        href="/library"
        class="rounded-md border border-neutral-800 px-4 py-2 text-sm hover:bg-neutral-900"
      >
        Ver canciones →
      </a>
    </div>

    {#if stats.tracks === 0}
      <p class="mt-8 rounded-md border border-amber-900/50 bg-amber-950/30 p-4 text-sm text-amber-200">
        Tu biblioteca está vacía. Copia ficheros de audio a
        <code class="rounded bg-neutral-900 px-1.5 py-0.5 text-xs">data/music/</code>
        y dale al botón de re-escanear. La ingesta desde Spotify llega en Fase 2.
      </p>
    {/if}
  {/if}
</div>
