<script lang="ts">
  import { pushBack } from '$lib/backstack.svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { Home, Music2, Disc3, Download, Settings, Shield, LogOut, Flame, HardDriveDownload, Radio } from 'lucide-svelte';
  import { jobs } from '$lib/jobs.svelte';
  import { auth } from '$lib/auth.svelte';

  // La altura real la lee el layout para calcular el hueco inferior del <main>
  // y para apoyar el reproductor justo encima, sin holguras a ojo.
  let { height = $bindable(0) }: { height?: number } = $props();

  let menuOpen = $state(false);
  let menuEl = $state<HTMLDivElement | null>(null);

  const items = $derived([
    { href: '/', label: 'Inicio', Icon: Home, badge: 0 },
    { href: '/library', label: 'Pistas', Icon: Music2, badge: 0 },
    { href: '/albums', label: 'Álbumes', Icon: Disc3, badge: 0 },
    { href: '/import', label: 'Importar', Icon: Download, badge: jobs.active },
    ...(auth.user?.is_admin ? [{ href: '/admin', label: 'Admin', Icon: Shield, badge: 0 }] : [])
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
    if (menuOpen && menuEl && !menuEl.contains(e.target as Node)) menuOpen = false;
  }

  // Atrás de Android cierra el menú de usuario.
  $effect(() => {
    if (menuOpen) return pushBack(() => (menuOpen = false));
  });

  $effect(() => {
    if (menuOpen) {
      document.addEventListener('click', onDocClick, true);
      return () => document.removeEventListener('click', onDocClick, true);
    }
  });
</script>

<!-- z-[45]: por encima del reproductor (z-40), para que el menú de usuario que
     se despliega hacia arriba no quede tapado por la barra de media; y por
     debajo de los diálogos y overlays (z-50+), que sí deben cubrirlo todo. -->
<nav
  bind:clientHeight={height}
  class="fixed inset-x-0 bottom-0 z-[45] border-t border-line bg-surface pb-[env(safe-area-inset-bottom)]"
>
  <div class="mx-auto flex max-w-5xl">
    {#each items as item}
      {@const active = isActive(item.href)}
      <a
        href={item.href}
        class="relative flex min-h-14 flex-1 flex-col items-center justify-center gap-1 pb-1.5 pt-2.5 text-xs font-medium transition-colors"
        class:text-accent={active}
        class:text-fg-muted={!active}
      >
        {#if active}<span class="absolute inset-x-[30%] top-0 h-0.5 rounded-full bg-accent"></span>{/if}
        <item.Icon size={22} strokeWidth={active ? 2.25 : 1.75} />
        <span>{item.label}</span>
        {#if item.badge > 0}
          <span class="absolute right-[18%] top-1.5 min-w-[1.1rem] rounded-full bg-accent px-1 text-center text-xs font-semibold leading-[1.1rem] text-accent-fg">
            {item.badge > 99 ? '99+' : item.badge}
          </span>
        {/if}
      </a>
    {/each}

    {#if auth.user}
      <div class="relative flex flex-1" bind:this={menuEl}>
        <button
          onclick={() => (menuOpen = !menuOpen)}
          class="flex min-h-14 flex-1 flex-col items-center justify-center gap-1 pb-1.5 pt-2.5 text-xs font-medium"
          class:text-accent={menuOpen}
          class:text-fg-muted={!menuOpen}
        >
          <span class="grid size-[22px] place-items-center rounded-full bg-surface-3 text-xs font-bold text-accent">
            {auth.user.username[0]?.toUpperCase()}
          </span>
          <span class="max-w-[60px] truncate">{auth.user.username}</span>
        </button>
        {#if menuOpen}
          <div class="absolute bottom-full right-2 mb-2 w-56 overflow-hidden rounded-xl border border-line bg-surface-2 shadow-xl">
            <div class="border-b border-line px-4 py-3 text-xs">
              <div class="truncate text-sm font-semibold text-fg">{auth.user.username}</div>
              <div class="truncate text-fg-subtle">{auth.user.email}</div>
              {#if auth.user.is_admin}
                <div class="mt-0.5 text-accent">administrador</div>
              {/if}
            </div>
            <a
              href="/live"
              onclick={() => (menuOpen = false)}
              class="flex min-h-11 items-center gap-3 px-4 text-sm text-fg hover:bg-surface-3"
            ><Radio size={16} /> Sonando ahora</a>
            <a
              href="/wrapped"
              onclick={() => (menuOpen = false)}
              class="flex min-h-11 items-center gap-3 px-4 text-sm text-fg hover:bg-surface-3"
            ><Flame size={16} /> Tu Wrapped</a>
            <a
              href="/downloads"
              onclick={() => (menuOpen = false)}
              class="flex min-h-11 items-center gap-3 px-4 text-sm text-fg hover:bg-surface-3"
            ><HardDriveDownload size={16} /> Descargas</a>
            <a
              href="/settings"
              onclick={() => (menuOpen = false)}
              class="flex min-h-11 items-center gap-3 px-4 text-sm text-fg hover:bg-surface-3"
            ><Settings size={16} /> Ajustes</a>
            <button
              onclick={logout}
              class="flex min-h-11 w-full items-center gap-3 px-4 text-left text-sm text-danger hover:bg-surface-3"
            ><LogOut size={16} /> Salir</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</nav>
