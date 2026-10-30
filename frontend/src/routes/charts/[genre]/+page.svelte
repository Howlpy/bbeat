<script lang="ts">
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { Play, Shuffle, TrendingUp } from 'lucide-svelte';
  import { api, type ChartTrack, type GenreChart, type Track } from '$lib/api';
  import { onReconnect } from '$lib/net.svelte';
  import { player } from '$lib/player.svelte';
  import TrackList from '$lib/components/TrackList.svelte';
  import ListenerAvatars from '$lib/components/ListenerAvatars.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';

  const genre = $derived(page.params.genre ?? '');

  let chart = $state<GenreChart | null>(null);
  let tracks = $state<Track[]>([]);
  let error = $state<string | null>(null);
  let loaded = $state(false);
  // 404: el género ya no cumple el mínimo de esta semana (no es un fallo).
  let notFound = $state(false);

  async function load() {
    try {
      const res = await api.chart(genre, 30);
      chart = res;
      tracks = res.items;
      error = null;
      notFound = false;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      notFound = /^404/.test(msg);
      error = notFound ? null : msg;
    } finally {
      loaded = true;
    }
  }

  onMount(() => {
    load();
    return onReconnect(() => {
      if (error) load();
    });
  });

  const asChart = (t: Track) => t as ChartTrack;
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

  // Ranking: "M escuchas · N oyentes" (corto para que quepa en móvil). Relleno: escuchas y periodo.
  const meta = (t: Track) => {
    const c = asChart(t);
    if (c.filler) {
      const when = c.window_days ? `${c.window_days} días` : 'histórico';
      return `${plural(c.plays, 'escucha', 'escuchas')} · ${when}`;
    }
    // Escuchas primero: si el móvil corta, los oyentes ya se ven en las iniciales.
    return `${plural(c.plays, 'escucha', 'escuchas')} · ${plural(c.listeners, 'oyente', 'oyentes')}`;
  };

  // Separador antes de la primera pista de relleno.
  const section = (t: Track, i: number) =>
    asChart(t).filler && !asChart(tracks[i - 1] ?? t).filler && i > 0
      ? 'Para completar · más escuchadas del género'
      : null;
  const numberFor = (t: Track, i: number) => asChart(t).rank ?? null;
</script>

<div class="page">
  <BackButton fallback="/" />

  {#if error}
    <ErrorState {error} />
  {:else if notFound}
    <EmptyState
      icon={TrendingUp}
      title="Aún no hay lista"
      text="Esta semana aún no hay suficiente música de este género."
    />
  {:else if !loaded}
    <Skeleton class="mb-2 h-8 w-56" />
    <Skeleton class="mb-6 h-4 w-72" />
    <div class="space-y-2">
      {#each Array(8) as _}<Skeleton class="h-14 w-full" />{/each}
    </div>
  {:else if chart && tracks.length > 0}
    <header class="mb-6">
      <h1 class="flex items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
        <TrendingUp size={22} class="flex-none text-accent" /> Top {chart.name}
      </h1>
      <p class="mt-1 text-sm text-fg-muted">Lo más escuchado en el servidor · últimos 7 días</p>
      <p class="mt-0.5 text-xs text-fg-subtle">Se actualiza con cada escucha</p>
      <div class="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" onclick={() => player.playTracks(tracks, 0)}>
          <Play size={16} fill="currentColor" /> Reproducir
        </Button>
        <Button onclick={() => player.playShuffled(tracks)}>
          <Shuffle size={16} /> Aleatorio
        </Button>
      </div>
    </header>
    <TrackList bind:tracks numbered {meta} {numberFor} sectionLabel={section} onchanged={load}>
      {#snippet trailing(t)}
        <ListenerAvatars users={asChart(t).listener_users ?? []} />
      {/snippet}
    </TrackList>
  {:else}
    <EmptyState
      icon={TrendingUp}
      title="Aún no hay lista"
      text="Esta semana aún no hay suficiente música de este género."
    />
  {/if}
</div>
