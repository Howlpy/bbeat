<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
  type Size = 'sm' | 'md' | 'lg';

  let {
    variant = 'secondary',
    size = 'md',
    icon = false,
    href,
    class: extra = '',
    children,
    ...rest
  }: {
    variant?: Variant;
    size?: Size;
    /** Botón circular solo-icono (área táctil mínima de 40px). */
    icon?: boolean;
    href?: string;
    class?: string;
    children?: Snippet;
  } & HTMLButtonAttributes = $props();

  const variants: Record<Variant, string> = {
    primary: 'bg-accent text-accent-fg hover:bg-accent-hover active:bg-accent-hover',
    secondary: 'border border-line-strong bg-surface-2 text-fg hover:bg-surface-3 active:bg-surface-3',
    ghost: 'text-fg-muted hover:bg-surface-2 hover:text-fg active:bg-surface-2',
    danger: 'border border-danger/40 text-danger hover:bg-danger/10 active:bg-danger/10'
  };
  // Alto táctil mínimo de 40px en móvil
  const sizes: Record<Size, string> = {
    sm: 'min-h-10 gap-1.5 px-3 text-sm sm:min-h-9',
    md: 'min-h-11 gap-2 px-4 text-sm sm:min-h-10',
    lg: 'min-h-12 gap-2 px-5 text-base'
  };
  const iconSizes: Record<Size, string> = {
    sm: 'size-10 sm:size-9',
    md: 'size-10',
    lg: 'size-12'
  };

  const cls = $derived(
    `inline-flex flex-none items-center justify-center font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
      icon ? `${iconSizes[size]} rounded-full` : `${sizes[size]} rounded-lg`
    } ${variants[variant]} ${extra}`
  );
</script>

{#if href}
  <a {href} class={cls}>{@render children?.()}</a>
{:else}
  <button type="button" class={cls} {...rest}>{@render children?.()}</button>
{/if}
