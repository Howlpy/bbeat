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
  import { prefs } from '$lib/prefs.svelte';

  let { children } = $props();

  const PUBLIC_ROUTES = ['/login', '/register'];
  const isPublicPage = $derived(PUBLIC_ROUTES.some((p) => page.url.pathname.startsWith(p)));

  // Alturas reales de las dos barras fijas de abajo. Medirlas (en vez de fijar
  // píxeles a ojo) es lo que garantiza que el player quede pegado a la navbar
  // sin hueco y que el contenido nunca quede tapado, salga la barra que salga.
  let navHeight = $state(0);
  let playerHeight = $state(0);
  let mainPadBottom = $derived(navHeight + (player.current ? playerHeight : 0));

  onMount(async () => {
    server.init();
    auth.init();

    // Si no hay sesión y no estamos en una página pública, ir al login
    if (!auth.isLoggedIn && !isPublicPage) {
      goto('/login');
      return;
    }

    // Los servicios de sesión los arranca el $effect de abajo, que además
    // cubre el login en caliente (goto('/') no vuelve a montar el layout).

    if (dev && 'serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/service-worker.js', { type: 'module' });
      } catch (e) {
        console.warn('[bbeat] SW register falló:', e);
      }
    }
  });

  // Servicios que necesitan sesión. Va en un $effect y no en onMount porque al
  // iniciar sesión se navega con goto('/'), que NO remonta el layout: con
  // onMount, quien acababa de entrar se quedaba sin polling de jobs, sin
  // descargas offline y sin sus preferencias hasta recargar la página.
  // Bandera simple, no reactiva: si fuese $state, el efecto se leería a sí
  // mismo y se reejecutaría sin necesidad.
  let sessionStarted = false;
  $effect(() => {
    if (!auth.isLoggedIn || sessionStarted) return;
    sessionStarted = true;
    jobs.start();
    offline.init();
    prefs.init();
    // En la app nativa, pedir permiso de notificaciones (Android 13+) para que
    // aparezca el control de media en la notificación/bloqueo.
    if (Capacitor.isNativePlatform()) {
      import('@capacitor/local-notifications')
        .then(({ LocalNotifications }) => LocalNotifications.requestPermissions())
        .catch(() => {});
    }
  });

  // Si el usuario hace logout en runtime, parar polling y redirigir
  $effect(() => {
    if (auth.initialized && !auth.isLoggedIn && !isPublicPage) {
      jobs.stop();
      prefs.clear();
      sessionStarted = false;
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
  <main class="min-h-screen" style:padding-bottom="{mainPadBottom}px">
    {#key page.url.pathname}
      <div in:fly={{ y: 10, duration: 220 }}>
        {@render children?.()}
      </div>
    {/key}
  </main>
  <!-- Orden en pantalla: el player va encima, la navbar debajo pegada al borde. -->
  <Player bottom={navHeight} bind:height={playerHeight} />
  <BottomNav bind:height={navHeight} />
{/if}
