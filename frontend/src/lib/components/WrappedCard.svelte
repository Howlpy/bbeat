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
  class="relative w-[360px] overflow-hidden rounded-2xl bg-gradient-to-br from-cyan-500 via-sky-700 to-slate-950 p-6 text-slate-50"
>
  <div class="mb-5 flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="grid size-8 place-items-center rounded-lg bg-white/15"><Flame size={18} /></span>
      <span class="text-lg font-black tracking-tight">bbeat</span>
    </div>
    <span class="rounded-full bg-black/25 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider">{rangeLabel}</span>
  </div>

  <p class="text-sm font-medium text-white/80">El wrapped de</p>
  <h2 class="mb-5 truncate text-3xl font-black">{username}</h2>

  <div class="mb-5 grid grid-cols-3 gap-2">
    <div class="rounded-xl bg-black/20 p-3 text-center">
      <div class="text-2xl font-black">{stats.total_plays}</div>
      <div class="text-[9px] uppercase tracking-wider text-white/70">plays</div>
    </div>
    <div class="rounded-xl bg-black/20 p-3 text-center">
      <div class="text-2xl font-black">{stats.total_minutes}</div>
      <div class="text-[9px] uppercase tracking-wider text-white/70">minutos</div>
    </div>
    <div class="rounded-xl bg-black/20 p-3 text-center">
      <div class="text-2xl font-black">{stats.streak_days}</div>
      <div class="text-[9px] uppercase tracking-wider text-white/70">días racha</div>
    </div>
  </div>

  <div class="space-y-2 text-sm">
    <div class="flex items-center gap-2">
      <Trophy size={15} class="flex-none text-amber-300" />
      <span class="text-white/70">Artista top:</span>
      <span class="truncate font-bold">{topArtist}</span>
    </div>
    <div class="flex items-center gap-2">
      <Music2 size={15} class="flex-none text-white/80" />
      <span class="text-white/70">Canción top:</span>
      <span class="truncate font-bold">{topTrack}</span>
    </div>
    <div class="flex items-center gap-2">
      <Clock size={15} class="flex-none text-white/80" />
      <span class="text-white/70">Pistas distintas:</span>
      <span class="font-bold">{stats.unique_tracks}</span>
    </div>
  </div>

  <p class="mt-5 text-center text-[10px] font-medium tracking-wider text-white/60">bbeat.howl.wtf</p>
</div>
