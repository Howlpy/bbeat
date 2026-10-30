<script lang="ts">
  // Bloque de carga plano y pulsante
  let { class: extra = '' }: { class?: string } = $props();
</script>

<div class="animate-pulse rounded-lg bg-surface-2 {extra}" aria-hidden="true"></div>
