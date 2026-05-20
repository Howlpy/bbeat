<script lang="ts">
  import { page } from '$app/state';
  import { player } from '$lib/player.svelte';
  import { jobs } from '$lib/jobs.svelte';

  const items = [
    { href: '/', label: 'Inicio', icon: '⌂', badge: () => 0 },
    { href: '/library', label: 'Pistas', icon: '♪', badge: () => 0 },
    { href: '/albums', label: 'Álbumes', icon: '◉', badge: () => 0 },
    { href: '/import', label: 'Importar', icon: '↓', badge: () => jobs.active },
    { href: '/settings', label: 'Ajustes', icon: '⚙', badge: () => 0 }
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
      {@const badge = item.badge()}
      <a
        href={item.href}
        class="relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs"
        class:text-emerald-400={isActive(item.href)}
        class:text-neutral-500={!isActive(item.href)}
      >
        <span class="text-lg leading-none">{item.icon}</span>
        <span>{item.label}</span>
        {#if badge > 0}
          <span
            class="absolute right-1/4 top-1 min-w-[1.1rem] rounded-full bg-sky-500 px-1 text-center text-[10px] font-semibold text-white"
          >
            {badge > 99 ? '99+' : badge}
          </span>
        {/if}
      </a>
    {/each}
  </div>
</nav>
