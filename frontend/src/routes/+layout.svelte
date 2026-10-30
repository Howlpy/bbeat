<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { fade } from 'svelte/transition';
  import { dev } from '$app/environment';
  import { afterNavigate, goto } from '$app/navigation';
  import { nav, popBack, trackNav } from '$lib/backstack.svelte';
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
  import { initNet, net, triggerReconnect } from '$lib/net.svelte';
  import { toast } from '$lib/toast.svelte';
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
    initNet();
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

  afterNavigate(trackNav);

  // Raíces: pestañas de la barra inferior. Desde ellas el atrás no retrocede.
  const ROOTS = ['/', '/search', '/library', '/import'];

  // Atrás de Android: 1) cierra overlays, 2) historial interno, 3) inicio,
  // 4) minimiza (nunca cierra la app).
  onMount(() => {
    if (!Capacitor.isNativePlatform()) return;
    let handle: { remove: () => Promise<void> } | null = null;
    let cancelled = false;
    import('@capacitor/app')
      .then(({ App }) =>
        App.addListener('backButton', () => {
          if (popBack()) return;
          const path = page.url.pathname;
          if (!ROOTS.includes(path) && nav.hasHistory) history.back();
          else if (path !== '/') goto('/');
          else App.minimizeApp();
        })
      )
      .then((h) => {
        if (cancelled) h.remove();
        else handle = h;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      handle?.remove();
    };
  });

  onDestroy(() => jobs.stop());
</script>

{#if isPublicPage}
  <main class="min-h-screen">{@render children?.()}</main>
{:else if !auth.initialized}
  <main class="grid min-h-screen place-items-center">
    <p class="text-sm text-fg-subtle">Cargando…</p>
  </main>
{:else}
  {#if !net.online}
    <div
      class="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-3 bg-warning px-3 py-1 pt-[calc(0.25rem+env(safe-area-inset-top))] text-xs font-semibold leading-5 text-accent-fg"
    >
      <button type="button" class="flex items-center gap-1.5" onclick={triggerReconnect}>
        <WifiOff size={11} /> Sin conexión · reintentar
      </button>
      <a href="/downloads" class="underline">Descargas</a>
    </div>
  {/if}
  {#if toast.msg}
    <div
      class="pointer-events-none fixed inset-x-0 bottom-36 z-[70] mx-auto w-fit max-w-[90vw] rounded-full border border-line-strong bg-surface-2 px-4 py-2.5 text-sm text-fg shadow-xl"
      transition:fade={{ duration: 150 }}
    >{toast.msg}</div>
  {/if}
  <main class="min-h-screen" style:padding-bottom="{mainPadBottom}px">
    {#key page.url.pathname}
      <div in:fade={{ duration: 100 }}>
        {@render children?.()}
      </div>
    {/key}
  </main>
  <!-- Orden en pantalla: el player va encima, la navbar debajo pegada al borde. -->
  <Player bottom={navHeight} bind:height={playerHeight} />
  <BottomNav bind:height={navHeight} />
{/if}
