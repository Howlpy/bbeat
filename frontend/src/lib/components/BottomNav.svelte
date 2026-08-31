<script lang="ts">
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
  class="fixed inset-x-0 bottom-0 z-[45] border-t border-slate-800 bg-slate-950/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
>
  <div class="mx-auto flex max-w-5xl">
    {#each items as item}
      {@const active = isActive(item.href)}
      <a
        href={item.href}
        class="relative flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] transition-colors"
        class:text-cyan-400={active}
        class:text-slate-500={!active}
      >
        <item.Icon size={20} strokeWidth={active ? 2.5 : 2} />
        <span>{item.label}</span>
        {#if item.badge > 0}
          <span class="absolute right-[20%] top-1 min-w-[1.1rem] rounded-full bg-cyan-500 px-1 text-center text-[10px] font-semibold text-slate-950">
            {item.badge > 99 ? '99+' : item.badge}
          </span>
        {/if}
      </a>
    {/each}

    {#if auth.user}
      <div class="relative flex flex-1" bind:this={menuEl}>
        <button
          onclick={() => (menuOpen = !menuOpen)}
          class="flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px]"
          class:text-cyan-400={menuOpen}
          class:text-slate-500={!menuOpen}
        >
          <span class="grid size-5 place-items-center rounded-full bg-slate-800 text-[10px] font-bold text-cyan-400">
            {auth.user.username[0]?.toUpperCase()}
          </span>
          <span class="max-w-[60px] truncate">{auth.user.username}</span>
        </button>
        {#if menuOpen}
          <div class="absolute bottom-full right-2 mb-2 w-48 overflow-hidden rounded border border-slate-800 bg-slate-900 shadow-xl">
            <div class="border-b border-slate-800 px-3 py-2 text-xs">
              <div class="truncate text-slate-300">{auth.user.username}</div>
              <div class="truncate text-slate-500">{auth.user.email}</div>
              {#if auth.user.is_admin}
                <div class="mt-0.5 text-cyan-400">administrador</div>
              {/if}
            </div>
            <a
              href="/live"
              onclick={() => (menuOpen = false)}
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            ><Radio size={16} /> Sonando ahora</a>
            <a
              href="/wrapped"
              onclick={() => (menuOpen = false)}
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            ><Flame size={16} /> Tu Wrapped</a>
            <a
              href="/downloads"
              onclick={() => (menuOpen = false)}
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            ><HardDriveDownload size={16} /> Descargas</a>
            <a
              href="/settings"
              onclick={() => (menuOpen = false)}
              class="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            ><Settings size={16} /> Ajustes</a>
            <button
              onclick={logout}
              class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 hover:bg-slate-800"
            ><LogOut size={16} /> Salir</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</nav>
