<script lang="ts">
  import { onMount } from 'svelte';
  import { Flame, ChevronRight } from 'lucide-svelte';
  import { api, type Wrapped, type WrappedPeriod } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { onReconnect } from '$lib/net.svelte';
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import Stories from '$lib/components/wrapped/Stories.svelte';
  import { PERIODS } from '$lib/components/wrapped/model';

  let data = $state<Wrapped | null>(null);
  let loadingId = $state<WrappedPeriod | null>(null);
  let emptyFor = $state<string | null>(null);
  let error = $state<string | null>(null);
  let last: WrappedPeriod | null = null;

  async function start(p: WrappedPeriod) {
    if (loadingId) return;
    last = p;
    loadingId = p;
    error = null;
    emptyFor = null;
    try {
      const w = await api.wrapped(p);
      if (w.total_plays === 0) emptyFor = PERIODS.find((x) => x.id === p)?.label.toLowerCase() ?? '';
      else data = w;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loadingId = null;
    }
  }

  onMount(() => onReconnect(() => error && last && start(last)));
</script>

{#if data}
  <Stories w={data} username={auth.user?.username ?? 'bbeat'} onclose={() => (data = null)} />
{/if}

<div class="page-narrow">
  <BackButton fallback="/" />
  <header class="mb-8 flex items-center gap-4">
    <span class="grid size-12 flex-none place-items-center rounded-xl bg-accent-soft text-accent">
      <Flame size={24} />
    </span>
    <div>
      <h1 class="page-title">Tu Wrapped</h1>
      <p class="text-sm text-fg-muted">Elige qué periodo quieres repasar</p>
    </div>
  </header>

  {#if error}
    <div class="mb-6"><ErrorState {error} /></div>
  {:else if emptyFor}
    <div class="mb-6">
      <EmptyState icon={Flame} title="Sin reproducciones {emptyFor}" text="Prueba otro periodo o dale al play." />
    </div>
  {/if}

  <div class="grid gap-3 sm:grid-cols-2">
    {#each PERIODS as p (p.id)}
      <button
        type="button"
        onclick={() => start(p.id)}
        disabled={loadingId !== null}
        class="group flex min-h-24 items-center justify-between rounded-2xl border border-line bg-surface p-5 text-left transition hover:bg-surface-2 active:bg-surface-2 disabled:opacity-60"
      >
        <span>
          <span class="block text-2xl font-extrabold tracking-tight">{p.label}</span>
          <span class="text-sm text-fg-muted">{p.sub}</span>
        </span>
        {#if loadingId === p.id}
          <Skeleton class="h-6 w-12" />
        {:else}
          <ChevronRight size={22} class="text-accent transition group-hover:translate-x-0.5" />
        {/if}
      </button>
    {/each}
  </div>
</div>
