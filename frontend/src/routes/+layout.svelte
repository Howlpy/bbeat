<script lang="ts">
  import { onMount } from 'svelte';
  import { dev } from '$app/environment';
  import '../app.css';
  import Player from '$lib/components/Player.svelte';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import { player } from '$lib/player.svelte';

  let { children } = $props();

  let mainPadBottom = $derived(player.current ? 'pb-36' : 'pb-20');

  // En prod SvelteKit registra el SW solo; en dev tenemos que hacerlo a mano
  // para poder probar PWA + background audio sin compilar.
  onMount(async () => {
    if (dev && 'serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/service-worker.js', { type: 'module' });
        console.log('[bbeat] service worker registrado (dev)');
      } catch (e) {
        console.warn('[bbeat] SW register falló:', e);
      }
    }
  });
</script>

<main class="min-h-screen {mainPadBottom}">
  {@render children?.()}
</main>

<BottomNav />
<Player />
