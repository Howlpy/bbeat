<script lang="ts">
  import { ArrowUpDown } from 'lucide-svelte';
  import { prefs } from '$lib/prefs.svelte';
  import { TRACK_SORTS, isTrackSort, type SortOption, type TrackSort } from '$lib/sort';

  let {
    prefKey,
    value = $bindable<TrackSort>('original'),
    options = TRACK_SORTS,
    originalLabel
  }: {
    /** Clave bajo la que se recuerda el orden de ESTA lista (p. ej. 'sort:album:12'). */
    prefKey: string;
    value?: TrackSort;
    options?: SortOption[];
    /** Texto de la opción 'original', que cambia según la lista. */
    originalLabel?: string;
  } = $props();

  const shown = $derived(
    originalLabel
      ? options.map((o) => (o.value === 'original' ? { ...o, label: originalLabel } : o))
      : options
  );

  // El orden guardado manda. Se reevalúa cuando cambia la clave (navegas a otra
  // playlist) y cuando llega el GET del servidor con lo elegido en otro sitio.
  $effect(() => {
    const saved = prefs.get(prefKey);
    value = saved && isTrackSort(saved) ? saved : 'original';
  });

  function onChange(e: Event) {
    const next = (e.target as HTMLSelectElement).value;
    if (!isTrackSort(next)) return;
    value = next;
    prefs.set(prefKey, next);
  }
</script>

<label class="flex items-center gap-1.5 text-xs text-slate-400">
  <ArrowUpDown size={14} class="flex-none text-slate-500" />
  <span class="sr-only">Ordenar por</span>
  <select
    value={value}
    onchange={onChange}
    class="rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
  >
    {#each shown as opt (opt.value)}
      <option value={opt.value}>{opt.label}</option>
    {/each}
  </select>
</label>
