<script lang="ts">
  import { onMount } from 'svelte';

  let setupComplete = $state<boolean | null>(null);

  onMount(async () => {
    const r = await fetch('/api/setup/status');
    const d = await r.json();
    setupComplete = d.setup_complete;
  });
</script>

<div class="mx-auto max-w-2xl px-4 pt-6">
  <h1 class="mb-4 text-2xl font-bold">Ajustes</h1>

  <section class="rounded-lg border border-neutral-800 bg-neutral-900 p-4">
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wider text-neutral-500">Setup</h2>
    {#if setupComplete === null}
      <p class="text-neutral-500">Comprobando…</p>
    {:else if setupComplete}
      <p class="text-emerald-400">✓ Configuración base completa.</p>
    {:else}
      <p class="text-amber-400">⚠ Configuración incompleta. Wizard llega en Fase 2.</p>
    {/if}
  </section>

  <p class="mt-6 text-xs text-neutral-600">
    Las opciones de descarga, calidad, rutas y credenciales se podrán editar
    aquí desde la Fase 2. Por ahora se configuran en <code class="bg-neutral-900 px-1">backend/.env</code>.
  </p>
</div>
