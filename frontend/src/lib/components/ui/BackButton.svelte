<script lang="ts">
  import { ArrowLeft } from 'lucide-svelte';
  import { goBack } from '$lib/backstack.svelte';

  // Volver al historial interno o, si no lo hay, a `fallback`.
  let { fallback = '/', label = 'Volver' }: { fallback?: string; label?: string } = $props();
</script>

<button
  type="button"
  onclick={() => goBack(fallback)}
  class="-ml-2 mb-4 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-sm text-fg-muted transition hover:bg-surface hover:text-fg"
  aria-label={label}
>
  <ArrowLeft size={17} /> {label}
</button>
