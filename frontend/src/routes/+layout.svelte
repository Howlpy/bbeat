<script lang="ts">
  import '../app.css';
  import Player from '$lib/components/Player.svelte';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import { player } from '$lib/player.svelte';

  let { children } = $props();

  let mainPadBottom = $derived(player.current ? 'pb-36' : 'pb-20');
</script>

<main class="min-h-screen {mainPadBottom}">
  {@render children?.()}
</main>

<BottomNav />
<Player />
