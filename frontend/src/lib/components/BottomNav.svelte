<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { player } from '$lib/player.svelte';
  import { jobs } from '$lib/jobs.svelte';
  import { auth } from '$lib/auth.svelte';

  let menuOpen = $state(false);
  let menuEl = $state<HTMLDivElement | null>(null);

  const items = $derived([
    { href: '/', label: 'Inicio', icon: '⌂', badge: 0 },
    { href: '/library', label: 'Pistas', icon: '♪', badge: 0 },
    { href: '/albums', label: 'Álbumes', icon: '◉', badge: 0 },
    { href: '/import', label: 'Importar', icon: '↓', badge: jobs.active },
    ...(auth.user?.is_admin
      ? [{ href: '/admin', label: 'Admin', icon: '⚙', badge: 0 }]
      : [])
  ]);

  function isActive(href: string): boolean {
    return href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
  }

  function logout() {
    auth.logout();
    menuOpen = false;
    goto('/login');
  }

  function onDocClick(e: MouseEvent) {
    if (menuOpen && menuEl && !menuEl.contains(e.target as Node)) {
      menuOpen = false;
    }
  }

  $effect(() => {
    if (menuOpen) {
      document.addEventListener('click', onDocClick, true);
      return () => document.removeEventListener('click', onDocClick, true);
    }
  });
</script>

<nav
  class="fixed inset-x-0 z-30 border-t border-neutral-800 bg-neutral-950/95 backdrop-blur"
  style:bottom={player.current ? '78px' : '0'}
>
  <div class="mx-auto flex max-w-5xl">
    {#each items as item}
      <a
        href={item.href}
        class="relative flex flex-1 flex-col items-center gap-0.5 py-2 text-xs"
        class:text-emerald-400={isActive(item.href)}
        class:text-neutral-500={!isActive(item.href)}
      >
        <span class="text-lg leading-none">{item.icon}</span>
        <span>{item.label}</span>
        {#if item.badge > 0}
          <span
            class="absolute right-1/4 top-1 min-w-[1.1rem] rounded-full bg-sky-500 px-1 text-center text-[10px] font-semibold text-white"
          >{item.badge > 99 ? '99+' : item.badge}</span>
        {/if}
      </a>
    {/each}

    <!-- Usuario / logout -->
    {#if auth.user}
      <div class="relative flex flex-1" bind:this={menuEl}>
        <button
          onclick={() => (menuOpen = !menuOpen)}
          class="flex flex-1 flex-col items-center gap-0.5 py-2 text-xs"
          class:text-emerald-400={menuOpen}
          class:text-neutral-500={!menuOpen}
        >
          <span class="grid size-5 place-items-center rounded-full bg-neutral-800 text-[10px] font-bold text-emerald-400">
            {auth.user.username[0]?.toUpperCase()}
          </span>
          <span class="max-w-[60px] truncate">{auth.user.username}</span>
        </button>
        {#if menuOpen}
          <div class="absolute bottom-full right-2 mb-2 w-44 overflow-hidden rounded-md border border-neutral-800 bg-neutral-900 shadow-xl">
            <div class="border-b border-neutral-800 px-3 py-2 text-xs text-neutral-400">
              <div class="truncate">{auth.user.email}</div>
              {#if auth.user.is_admin}
                <div class="mt-0.5 text-amber-400">administrador</div>
              {/if}
            </div>
            <a
              href="/settings"
              onclick={() => (menuOpen = false)}
              class="block px-3 py-2 text-sm hover:bg-neutral-800"
            >⚙ Ajustes</a>
            <button
              onclick={logout}
              class="block w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-neutral-800"
            >↩ Salir</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</nav>
