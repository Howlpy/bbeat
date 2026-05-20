<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { dev } from '$app/environment';
  import '../app.css';
  import Player from '$lib/components/Player.svelte';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import { player } from '$lib/player.svelte';
  import { jobs } from '$lib/jobs.svelte';

  let { children } = $props();

  let mainPadBottom = $derived(player.current ? 'pb-36' : 'pb-20');

  onMount(async () => {
    // Polling global de jobs para el badge de la nav
    jobs.start();

    // SvelteKit auto-registra el SW en prod; en dev lo hago a mano.
    if (dev && 'serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/service-worker.js', { type: 'module' });
      } catch (e) {
        console.warn('[bbeat] SW register falló:', e);
      }
    }
  });

  onDestroy(() => jobs.stop());
</script>

<main class="min-h-screen {mainPadBottom}">
  {@render children?.()}
</main>

<BottomNav />
<Player />
