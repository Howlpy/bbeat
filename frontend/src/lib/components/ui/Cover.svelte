<script lang="ts">
  import type { Snippet } from 'svelte';

  // Carátula con fallback plano (icono o iniciales) cuando no hay imagen
  let {
    src,
    class: extra = '',
    children
  }: {
    src?: string | null;
    class?: string;
    /** Contenido del fallback (icono o iniciales). */
    children?: Snippet;
  } = $props();
</script>

{#if src}
  <img loading="lazy" decoding="async" {src} alt="" class="aspect-square bg-surface-2 object-cover {extra}" />
{:else}
  <div class="grid aspect-square place-items-center bg-surface-2 text-fg-subtle {extra}">
    {@render children?.()}
  </div>
{/if}
