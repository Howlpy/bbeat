<script lang="ts">
  import { onMount } from 'svelte';
  import { Radio, Music2, Monitor, Smartphone, Flame, History } from 'lucide-svelte';
  import { api, type Track, type NowPlaying } from '$lib/api';
  import { player } from '$lib/player.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';

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

    // Algunos proxies bufferizan SSE. El snapshot cada 3 s mantiene el feed
    // en directo de forma fiable también detrás de Cloudflare.
    let stopped = false;
    const refreshLive = async () => {
      try {
        const result = await api.nowPlayingSnapshot();
        if (!stopped) {
          live = result.items;
          connected = true;
        }
      } catch {
        if (!stopped) connected = false;
      }
    };
    refreshLive();
    const liveTimer = setInterval(refreshLive, 3_000);

    // Refresca los "hace X" cada 15s.
    const tick = setInterval(() => (now = Date.now()), 15_000);

    return () => {
      stopped = true;
      clearInterval(liveTimer);
      clearInterval(tick);
    };
  });
</script>

<div class="page-narrow">
  <header class="mb-8 flex items-center gap-4">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-accent-soft text-accent">
      <Radio size={24} />
    </span>
    <div>
      <h1 class="page-title">Sonando ahora</h1>
      <p class="flex items-center gap-1.5 text-sm text-fg-muted">
        <span class="inline-block size-2 rounded-full {connected ? 'animate-pulse bg-success' : 'bg-line-strong'}"></span>
        {connected ? 'en directo' : 'conectando…'} · qué suena en el server
      </p>
    </div>
  </header>

  <!-- Feed en vivo -->
  <section class="mb-10">
    {#if live.length === 0}
      <EmptyState icon={Radio} title="No suena nada ahora mismo" text="Dale al play y aparecerás aquí." />
    {:else}
      <ul class="space-y-2">
        {#each live as p (p.user_id)}
          <li class="flex items-center gap-3 rounded-xl border border-line bg-surface px-3 py-3">
            {#if p.track.cover_url}
              <img loading="lazy" decoding="async" src={p.track.cover_url} alt="" class="size-12 flex-none rounded-lg object-cover" />
            {:else}
              <div class="grid size-12 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle"><Music2 size={16} /></div>
            {/if}
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="grid size-5 flex-none place-items-center rounded-full bg-surface-2 text-xs font-bold text-accent">
                  {p.username[0]?.toUpperCase()}
                </span>
                <span class="truncate text-sm font-medium text-accent">{p.username}</span>
                <span
                  class="flex-none rounded-full border px-2 py-px text-xs uppercase tracking-wide {p.source === 'web'
                    ? 'border-accent/40 text-accent'
                    : 'border-warning/40 text-warning'}"
                  title={p.source === 'web' ? 'Reproductor web' : 'App Subsonic'}
                >
                  {#if p.source === 'web'}<Monitor size={12} class="mr-1 inline" />web{:else}<Smartphone size={12} class="mr-1 inline" />app{/if}
                </span>
              </div>
              <button
                onclick={() => player.playTracks([p.track], 0)}
                class="block max-w-full truncate text-left text-sm hover:underline"
              >{p.track.title}</button>
              <div class="truncate text-xs text-fg-subtle">{p.track.artist_name}</div>
            </div>
            <span class="flex-none self-start text-xs text-fg-subtle">{relTime(p.started_at)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if activity.length > 0}
    <section class="mb-10">
      <h2 class="section-title mb-3">
        <History size={14} class="text-accent" /> Historial reciente
      </h2>
      <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {#each activity as item, i (`${item.played_at}-${item.id}-${i}`)}
          <li>
            <button
              onclick={() => player.playTracks(activity, i)}
              class="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
            >
              {#if item.cover_url}
                <img loading="lazy" decoding="async" src={item.cover_url} alt="" class="size-10 flex-none rounded-lg object-cover" />
              {:else}
                <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle"><Music2 size={14} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{item.title}</div>
                <div class="truncate text-xs text-fg-subtle">
                  <span class="text-accent">{item.username}</span> · {item.artist_name}
                </div>
              </div>
              <span class="flex-none text-xs text-fg-subtle">{relTime(item.played_at)}</span>
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  <!-- Top del server (histórico) -->
  {#if serverTop.length > 0}
    <section>
      <h2 class="section-title mb-3">
        <Flame size={14} class="text-accent" /> Top del server
      </h2>
      <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {#each serverTop as t, i (t.id)}
          <li>
            <button
              onclick={() => player.playTracks(serverTop, i)}
              class="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2"
            >
              <span class="w-5 flex-none text-center text-xs tabular-nums text-fg-subtle">{i + 1}</span>
              {#if t.cover_url}
                <img loading="lazy" decoding="async" src={t.cover_url} alt="" class="size-10 flex-none rounded-lg object-cover" />
              {:else}
                <div class="grid size-10 flex-none place-items-center rounded-lg bg-surface-2 text-fg-subtle"><Music2 size={14} /></div>
              {/if}
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm">{t.title}</div>
                <div class="truncate text-xs text-fg-subtle">{t.artist_name}</div>
              </div>
              <span class="flex-none text-xs text-fg-subtle">{t.plays}×</span>
            </button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>
