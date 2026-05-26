<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { fly } from 'svelte/transition';
  import { dev } from '$app/environment';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import '../app.css';
  import Player from '$lib/components/Player.svelte';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import { WifiOff } from 'lucide-svelte';
  import { Capacitor } from '@capacitor/core';
  import { player } from '$lib/player.svelte';
  import { jobs } from '$lib/jobs.svelte';
  import { auth } from '$lib/auth.svelte';
  import { offline } from '$lib/offline.svelte';
  import { net } from '$lib/net.svelte';
  import { server } from '$lib/server.svelte';

  let { children } = $props();

  const PUBLIC_ROUTES = ['/login', '/register'];
  const isPublicPage = $derived(PUBLIC_ROUTES.some((p) => page.url.pathname.startsWith(p)));

  let mainPadBottom = $derived(player.current ? 'pb-36' : 'pb-20');

  onMount(async () => {
    server.init();
    auth.init();

    // Si no hay sesión y no estamos en una página pública, ir al login
    if (!auth.isLoggedIn && !isPublicPage) {
      goto('/login');
      return;
    }

    // Polling de jobs + cargar descargas offline solo si hay sesión
    if (auth.isLoggedIn) {
      jobs.start();
      offline.init();
      // En la app nativa, pedir permiso de notificaciones (Android 13+) para que
      // aparezca el control de media en la notificación/bloqueo.
      if (Capacitor.isNativePlatform()) {
        const { LocalNotifications } = await import('@capacitor/local-notifications');
        LocalNotifications.requestPermissions().catch(() => {});
      }
    }

    if (dev && 'serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/service-worker.js', { type: 'module' });
      } catch (e) {
        console.warn('[bbeat] SW register falló:', e);
      }
    }
  });

  // Si el usuario hace logout en runtime, parar polling y redirigir
  $effect(() => {
    if (auth.initialized && !auth.isLoggedIn && !isPublicPage) {
      jobs.stop();
      goto('/login');
    }
  });

  onDestroy(() => jobs.stop());
</script>

{#if isPublicPage}
  <main class="min-h-screen">{@render children?.()}</main>
{:else if !auth.initialized}
  <main class="grid min-h-screen place-items-center">
    <p class="text-slate-500">Cargando…</p>
  </main>
{:else}
  {#if !net.online}
    <a
      href="/downloads"
      class="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-2 bg-amber-600/95 px-3 py-1.5 text-xs font-medium text-amber-50 backdrop-blur"
    >
      <WifiOff size={14} /> Sin conexión · toca para ir a Descargas
    </a>
  {/if}
  <main class="min-h-screen {mainPadBottom}">
    {#key page.url.pathname}
      <div in:fly={{ y: 10, duration: 220 }}>
        {@render children?.()}
      </div>
    {/key}
  </main>
  <BottomNav />
  <Player />
{/if}
