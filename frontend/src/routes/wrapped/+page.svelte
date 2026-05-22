<script lang="ts">
  import { onMount } from 'svelte';
  import { Flame, Clock, Users, Heart, Music2, Radio, Trophy } from 'lucide-svelte';
  import { api, type Track } from '$lib/api';
  import { player } from '$lib/player.svelte';

  type Stats = {
    total_plays: number;
    total_minutes: number;
    unique_tracks: number;
    liked_count: number;
    top_tracks: (Track & { plays: number })[];
    top_artists: { id: number; name: string; plays: number }[];
  };

  let stats = $state<Stats | null>(null);
  let serverTop = $state<(Track & { plays: number })[]>([]);
  let activity = $state<(Track & { username: string; played_at: string | null })[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  async function load() {
    try {
      const [s, st, act] = await Promise.all([
        api.myStats(),
        api.topTracks({ scope: 'server', limit: 10 }).catch(() => ({ items: [] })),
        api.activity(20).catch(() => ({ items: [] }))
      ]);
      stats = s;
      serverTop = st.items;
      activity = act.items;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }
  onMount(load);

  function relTime(iso: string | null): string {
    if (!iso) return '';
    const d = (Date.now() - new Date(iso + 'Z').getTime()) / 1000;
    if (d < 60) return 'ahora';
    if (d < 3600) return `hace ${Math.floor(d / 60)} min`;
    if (d < 86400) return `hace ${Math.floor(d / 3600)} h`;
    return `hace ${Math.floor(d / 86400)} d`;
  }
</script>

<div class="mx-auto max-w-3xl px-4 pt-6 pb-8">
  <header class="mb-6 flex items-center gap-3">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-sky-700 text-slate-950">
      <Flame size={24} />
    </span>
    <div>
      <h1 class="text-2xl font-bold">Tu Wrapped</h1>
      <p class="text-xs text-slate-500">tus números en bbeat + lo que suena en el server</p>
    </div>
  </header>

  {#if error}
    <p class="text-red-400">{error}</p>
  {:else if loading}
    <p class="text-slate-500">Cargando…</p>
  {:else if stats && stats.total_plays === 0}
    <div class="rounded-md border border-dashed border-slate-800 p-8 text-center text-sm text-slate-400">
      Aún no hay reproducciones registradas. Dale al play y vuelve 😎
    </div>
  {:else if stats}
    <!-- Hero -->
    <section class="mb-8 grid grid-cols-3 gap-3">
      <div class="rounded-xl border border-cyan-900/40 bg-cyan-950/20 p-4 text-center">
        <Flame size={18} class="mx-auto mb-1 text-cyan-400" />
        <div class="text-2xl font-bold text-cyan-400">{stats.total_plays}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">plays</div>
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-center">
        <Clock size={18} class="mx-auto mb-1 text-slate-400" />
        <div class="text-2xl font-bold">{stats.total_minutes}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">minutos</div>
      </div>
      <div class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-center">
        <Music2 size={18} class="mx-auto mb-1 text-slate-400" />
        <div class="text-2xl font-bold">{stats.unique_tracks}</div>
        <div class="text-[10px] uppercase tracking-wider text-slate-500">pistas</div>
      </div>
    </section>

    <!-- Tus top tracks -->
    {#if stats.top_tracks.length > 0}
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Trophy size={14} class="text-cyan-400" /> Tus más escuchadas
        </h2>
        <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
          {#each stats.top_tracks as t, i (t.id)}
            <li>
              <button
                onclick={() => stats && player.playTracks(stats.top_tracks, i)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
              >
                <span class="w-5 flex-none text-center font-mono text-xs text-slate-600">{i + 1}</span>
                {#if t.cover_url}
                  <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={14} /></div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-slate-500">{t.artist_name}</div>
                </div>
                <span class="flex-none text-xs text-slate-500">{t.plays}×</span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Tus top artistas -->
    {#if stats.top_artists.length > 0}
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Users size={14} class="text-cyan-400" /> Tus artistas top
        </h2>
        <div class="flex flex-wrap gap-2">
          {#each stats.top_artists as a, i (a.id)}
            <a
              href="/artists/{a.id}"
              class="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm transition hover:border-cyan-700/50"
            >
              <span class="font-mono text-xs text-slate-600">{i + 1}</span>
              {a.name}
              <span class="text-xs text-cyan-400">{a.plays}×</span>
            </a>
          {/each}
        </div>
      </section>
    {/if}

    <!-- Top del server -->
    {#if serverTop.length > 0}
      <section class="mb-8">
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Flame size={14} class="text-cyan-400" /> Top del server
        </h2>
        <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
          {#each serverTop as t, i (t.id)}
            <li>
              <button
                onclick={() => player.playTracks(serverTop, i)}
                class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
              >
                <span class="w-5 flex-none text-center font-mono text-xs text-slate-600">{i + 1}</span>
                {#if t.cover_url}
                  <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
                {:else}
                  <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={14} /></div>
                {/if}
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm">{t.title}</div>
                  <div class="truncate text-xs text-slate-500">{t.artist_name}</div>
                </div>
                <span class="flex-none text-xs text-slate-500">{t.plays}×</span>
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <!-- Sonando en el server -->
    {#if activity.length > 0}
      <section>
        <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
          <Radio size={14} class="text-cyan-400" /> Sonando en el server
        </h2>
        <ul class="space-y-1.5">
          {#each activity as a (`${a.id}-${a.played_at}`)}
            <li class="flex items-center gap-3 rounded border border-slate-800/60 bg-slate-900/40 px-3 py-2">
              {#if a.cover_url}
                <img src={a.cover_url} alt="" class="size-9 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-9 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={13} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{a.title}</div>
                <div class="truncate text-xs text-slate-500">
                  <span class="text-cyan-400">{a.username}</span> · {a.artist_name}
                </div>
              </div>
              <span class="flex-none text-[10px] text-slate-600">{relTime(a.played_at)}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  {/if}
</div>
