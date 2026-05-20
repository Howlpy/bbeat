<script lang="ts">
  import { onMount } from 'svelte';

  let health = $state<{ status: string; version: string; setup_complete: boolean } | null>(null);
  let error = $state<string | null>(null);

  onMount(async () => {
    try {
      const res = await fetch('/api/health');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      health = await res.json();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Error desconocido';
    }
  });
</script>

<div class="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
  <h1 class="text-5xl font-bold tracking-tight">
    <span class="text-emerald-400">B</span>beat
  </h1>
  <p class="text-neutral-400">Tu servidor de música personal</p>

  <div class="mt-6 w-full max-w-md rounded-lg border border-neutral-800 bg-neutral-900 p-4">
    <h2 class="mb-3 text-sm font-semibold uppercase tracking-wider text-neutral-500">
      Estado del backend
    </h2>
    {#if error}
      <p class="text-red-400">⚠️ {error}</p>
      <p class="mt-2 text-xs text-neutral-500">¿Está el backend corriendo en :8787?</p>
    {:else if health}
      <ul class="space-y-1 text-sm">
        <li>
          <span class="text-neutral-500">Status:</span>
          <span class="text-emerald-400">{health.status}</span>
        </li>
        <li>
          <span class="text-neutral-500">Versión:</span>
          <span>{health.version}</span>
        </li>
        <li>
          <span class="text-neutral-500">Setup:</span>
          {#if health.setup_complete}
            <span class="text-emerald-400">completo</span>
          {:else}
            <span class="text-amber-400">pendiente — abrir wizard</span>
          {/if}
        </li>
      </ul>
    {:else}
      <p class="text-neutral-500">Cargando…</p>
    {/if}
  </div>

  <p class="text-xs text-neutral-600">Fase 0 — skeleton</p>
</div>
