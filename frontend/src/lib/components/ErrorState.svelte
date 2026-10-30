<script lang="ts">
  import { OFFLINE_MESSAGE } from '$lib/net.svelte';
  import OfflineEmpty from './OfflineEmpty.svelte';

  let { error }: { error: string } = $props();
</script>

{#if error === OFFLINE_MESSAGE}
  <OfflineEmpty />
{:else}
  <p class="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>
{/if}
