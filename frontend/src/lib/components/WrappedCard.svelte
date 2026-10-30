<script lang="ts">
  import { Flame, Clock, Music2, Trophy } from 'lucide-svelte';
  import type { MyStats } from '$lib/api';

  let { stats, username, rangeLabel }: { stats: MyStats; username: string; rangeLabel: string } =
    $props();

  const topArtist = $derived(stats.top_artists[0]?.name ?? '—');
  const topTrack = $derived(stats.top_tracks[0]?.title ?? '—');
</script>

<!-- Tarjeta con diseño fijo (no responsive) para exportar a imagen 1:1. -->
<div
  class="relative w-[360px] overflow-hidden rounded-xl border border-line bg-surface p-6 text-fg"
>
  <div class="mb-5 flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent"><Flame size={18} /></span>
      <span class="text-lg font-black tracking-tight">bbeat</span>
    </div>
    <span class="rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider">{rangeLabel}</span>
  </div>

  <p class="text-sm font-medium text-fg-muted">El wrapped de</p>
  <h2 class="mb-5 truncate text-3xl font-black">{username}</h2>

  <div class="mb-5 grid grid-cols-3 gap-2">
    <div class="rounded-xl bg-surface-2 p-3 text-center">
      <div class="text-2xl font-black tabular-nums text-accent">{stats.total_plays}</div>
      <div class="text-xs uppercase tracking-wider text-fg-muted">plays</div>
    </div>
    <div class="rounded-xl bg-surface-2 p-3 text-center">
      <div class="text-2xl font-black tabular-nums">{stats.total_minutes}</div>
      <div class="text-xs uppercase tracking-wider text-fg-muted">minutos</div>
    </div>
    <div class="rounded-xl bg-surface-2 p-3 text-center">
      <div class="text-2xl font-black tabular-nums">{stats.streak_days}</div>
      <div class="text-xs uppercase tracking-wider text-fg-muted">días racha</div>
    </div>
  </div>

  <div class="space-y-2 text-sm">
    <div class="flex items-center gap-2">
      <Trophy size={15} class="flex-none text-warning" />
      <span class="text-fg-muted">Artista top:</span>
      <span class="truncate font-bold">{topArtist}</span>
    </div>
    <div class="flex items-center gap-2">
      <Music2 size={15} class="flex-none text-fg-muted" />
      <span class="text-fg-muted">Canción top:</span>
      <span class="truncate font-bold">{topTrack}</span>
    </div>
    <div class="flex items-center gap-2">
      <Clock size={15} class="flex-none text-fg-muted" />
      <span class="text-fg-muted">Pistas distintas:</span>
      <span class="font-bold">{stats.unique_tracks}</span>
    </div>
  </div>

  <p class="mt-5 text-center text-xs font-medium tracking-wider text-fg-subtle">bbeat.howl.wtf</p>
</div>
