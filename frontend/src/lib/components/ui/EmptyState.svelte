<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    icon: Icon,
    title,
    text,
    children
  }: {
    /** Icono de lucide-svelte. */
    icon?: any;
    title: string;
    text?: string;
    /** Acciones opcionales (botones) bajo el texto. */
    children?: Snippet;
  } = $props();
</script>

<div class="flex flex-col items-center rounded-xl border border-dashed border-line px-6 py-10 text-center">
  {#if Icon}
    <span class="mb-3 grid size-12 place-items-center rounded-full bg-surface-2 text-fg-subtle">
      <Icon size={22} />
    </span>
  {/if}
  <p class="font-semibold">{title}</p>
  {#if text}<p class="mt-1 max-w-sm text-sm text-fg-muted">{text}</p>{/if}
  {#if children}<div class="mt-4 flex flex-wrap justify-center gap-2">{@render children()}</div>{/if}
</div>
