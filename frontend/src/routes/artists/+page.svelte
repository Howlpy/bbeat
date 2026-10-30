<script lang="ts">
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import { api, type Artist } from '$lib/api';
  import { initials } from '$lib/visual';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import { Mic2 } from 'lucide-svelte';

  let artists = $state<Artist[]>([]);
  let error = $state<string | null>(null);
  let loaded = $state(false);

  async function load() {
    try {
      const res = await api.artists();
      artists = res.items;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    load();
    return onReconnect(load);
  });
</script>

<div class="page-narrow">
  <h1 class="page-title mb-6">Artistas</h1>

  {#if error}
    <ErrorState {error} />
  {:else if !loaded}
    <div class="space-y-2">
      {#each Array(8) as _}<Skeleton class="h-16 w-full" />{/each}
    </div>
  {:else if artists.length === 0}
    <EmptyState icon={Mic2} title="Sin artistas todavía" text="Importa música y aparecerán aquí." />
  {:else}
    <ul class="divide-y divide-line">
      {#each artists as artist}
        <li>
          <a href="/artists/{artist.id}" class="flex min-h-16 items-center gap-3 px-2 py-2.5 hover:bg-surface">
            <span
              class="grid size-11 flex-none place-items-center rounded-full bg-surface-2 text-sm font-bold text-fg-muted"
            >{initials(artist.name)}</span>
            <div class="min-w-0 flex-1">
              <div class="truncate font-semibold">{artist.name}</div>
              <div class="text-xs text-fg-muted">
                {artist.album_count} álb · {artist.track_count} {artist.track_count === 1 ? 'pista' : 'pistas'}
              </div>
            </div>
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</div>
