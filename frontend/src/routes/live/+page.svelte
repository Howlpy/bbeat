<script lang="ts">
  import { onMount } from 'svelte';
  import { Radio, Music2, Monitor, Smartphone, Flame, History } from 'lucide-svelte';
  import { api, type Track, type NowPlaying } from '$lib/api';
  import { player } from '$lib/player.svelte';

  let live = $state<NowPlaying[]>([]);
  let serverTop = $state<(Track & { plays: number })[]>([]);
  let activity = $state<(Track & { username: string; played_at: string | null })[]>([]);
  let connected = $state(false);
  let now = $state(Date.now());

  function relTime(iso: string | null): string {
    if (!iso) return '';
    const d = (now - new Date(iso + 'Z').getTime()) / 1000;
    if (d < 60) return 'justo ahora';
    if (d < 3600) return `hace ${Math.floor(d / 60)} min`;
    if (d < 86400) return `hace ${Math.floor(d / 3600)} h`;
    return `hace ${Math.floor(d / 86400)} d`;
  }

  onMount(() => {
    Promise.all([
      api.topTracks({ scope: 'server', limit: 10 }),
      api.activity(50)
    ]).then(([top, recent]) => {
      serverTop = top.items;
      activity = recent.items;
    }).catch(() => {});

    const es = api.nowPlayingStream((items) => {
      live = items;
      connected = true;
    });
    es.onerror = () => (connected = false);
    es.onopen = () => (connected = true);

    // Refresca los "hace X" cada 15s.
    const tick = setInterval(() => (now = Date.now()), 15_000);

    return () => {
      es.close();
      clearInterval(tick);
    };
  });
</script>

<div class="mx-auto max-w-3xl px-4 pt-6 pb-8">
  <header class="mb-6 flex items-center gap-3">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-gradient-to-br from-fuchsia-500 to-purple-700 text-slate-950">
      <Radio size={24} />
    </span>
    <div>
      <h1 class="text-2xl font-bold">Sonando ahora</h1>
      <p class="flex items-center gap-1.5 text-xs text-slate-500">
        <span class="inline-block size-2 rounded-full {connected ? 'animate-pulse bg-emerald-500' : 'bg-slate-600'}"></span>
        {connected ? 'en directo' : 'conectando…'} · qué suena en el server
      </p>
    </div>
  </header>

  <!-- Feed en vivo -->
  <section class="mb-8">
    {#if live.length === 0}
      <div class="rounded-md border border-dashed border-slate-800 p-8 text-center text-sm text-slate-400">
        Ahora mismo no suena nada en el server. Dale al play 🎧
      </div>
    {:else}
      <ul class="space-y-2">
        {#each live as p (p.user_id)}
          <li class="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2.5">
            {#if p.track.cover_url}
              <img loading="lazy" decoding="async" src={p.track.cover_url} alt="" class="size-12 flex-none rounded object-cover" />
            {:else}
              <div class="grid size-12 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={16} /></div>
            {/if}
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="grid size-5 flex-none place-items-center rounded-full bg-slate-800 text-[10px] font-bold text-fuchsia-400">
                  {p.username[0]?.toUpperCase()}
                </span>
                <span class="truncate text-sm font-medium text-fuchsia-300">{p.username}</span>
                <span
                  class="flex-none rounded-full border px-1.5 py-px text-[9px] uppercase tracking-wide {p.source === 'web'
                    ? 'border-cyan-800 text-cyan-400'
                    : 'border-amber-800 text-amber-400'}"
                  title={p.source === 'web' ? 'Reproductor web' : 'App Subsonic'}
                >
                  {#if p.source === 'web'}<Monitor size={9} class="mr-0.5 inline" />web{:else}<Smartphone size={9} class="mr-0.5 inline" />app{/if}
                </span>
              </div>
              <button
                onclick={() => player.playTracks([p.track], 0)}
                class="block max-w-full truncate text-left text-sm hover:underline"
              >{p.track.title}</button>
              <div class="truncate text-xs text-slate-500">{p.track.artist_name}</div>
            </div>
            <span class="flex-none self-start text-[10px] text-slate-600">{relTime(p.started_at)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if activity.length > 0}
    <section class="mb-8">
      <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
        <History size={14} class="text-cyan-400" /> Historial reciente
      </h2>
      <ul class="divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900/40">
        {#each activity as item, i (`${item.played_at}-${item.id}-${i}`)}
          <li>
            <button
              onclick={() => player.playTracks(activity, i)}
              class="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-800/60"
            >
              {#if item.cover_url}
                <img loading="lazy" decoding="async" src={item.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
              {:else}
                <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={14} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{item.title}</div>
                <div class="truncate text-xs text-slate-500">
                  <span class="text-fuchsia-400">{item.username}</span> · {item.artist_name}
                </div>
              </div>
              <span class="flex-none text-[10px] text-slate-600">{relTime(item.played_at)}</span>
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <!-- Top del server (histórico) -->
  {#if serverTop.length > 0}
    <section>
      <h2 class="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-slate-400">
        <Flame size={14} class="text-fuchsia-400" /> Top del server
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
                <img loading="lazy" decoding="async" src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
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
</div>
