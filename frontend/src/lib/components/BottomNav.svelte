<script lang="ts">
  import { page } from '$app/state';
  import { player } from '$lib/player.svelte';

  const items = [
    { href: '/', label: 'Inicio', icon: '⌂' },
    { href: '/library', label: 'Pistas', icon: '♪' },
    { href: '/albums', label: 'Álbumes', icon: '◉' },
    { href: '/import', label: 'Importar', icon: '↓' },
    { href: '/settings', label: 'Ajustes', icon: '⚙' }
  ];

  function isActive(href: string): boolean {
    return href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
  }
</script>

<nav
  class="fixed inset-x-0 z-30 border-t border-neutral-800 bg-neutral-950/95 backdrop-blur"
  class:bottom-0={!player.current}
  style:bottom={player.current ? '78px' : '0'}
>
  <div class="mx-auto flex max-w-5xl">
    {#each items as item}
      <a
        href={item.href}
        class="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs"
        class:text-emerald-400={isActive(item.href)}
        class:text-neutral-500={!isActive(item.href)}
      >
        <span class="text-lg leading-none">{item.icon}</span>
        <span>{item.label}</span>
      </a>
    {/each}
  </div>
</nav>
