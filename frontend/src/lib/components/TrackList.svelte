<script lang="ts">
  import { player } from '$lib/player.svelte';
  import { formatDuration, type Track } from '$lib/api';

  let { tracks, showAlbum = true }: { tracks: Track[]; showAlbum?: boolean } = $props();

  function play(i: number) {
    player.playTracks(tracks, i);
  }
</script>

<ul class="divide-y divide-neutral-900">
  {#each tracks as t, i}
    {@const isCurrent = player.current?.id === t.id}
    <li>
      <button
        onclick={() => play(i)}
        class="flex w-full items-center gap-3 px-2 py-2 text-left hover:bg-neutral-900"
        class:bg-neutral-900={isCurrent}
      >
        {#if t.cover_url}
          <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
        {:else}
          <div class="grid size-10 flex-none place-items-center rounded bg-neutral-800 text-neutral-600">
            {t.track_number ?? '♪'}
          </div>
        {/if}
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm" class:text-emerald-400={isCurrent}>{t.title}</div>
          <div class="truncate text-xs text-neutral-500">
            {t.artist_name}{#if showAlbum && t.album_title} · {t.album_title}{/if}
          </div>
        </div>
        <span class="flex-none font-mono text-xs text-neutral-500">
          {formatDuration(t.duration_ms)}
        </span>
      </button>
    </li>
  {/each}
</ul>
