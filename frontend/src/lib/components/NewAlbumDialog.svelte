<script lang="ts">
  import { goto } from '$app/navigation';
  import { X } from 'lucide-svelte';
  import { api } from '$lib/api';

  let {
    onclose,
    oncreated
  }: { onclose: () => void; oncreated?: () => void } = $props();

  let title = $state('');
  let artist = $state('');
  let year = $state('');
  let saving = $state(false);
  let error = $state<string | null>(null);

  async function create() {
    if (!title.trim()) return;
    saving = true;
    error = null;
    try {
      const r = await api.createAlbum({
        title: title.trim(),
        artist: artist.trim() || 'Various Artists',
        year: year ? Number(year) || undefined : undefined,
        kind: 'playlist'
      });
      oncreated?.();
      onclose();
      if (r.id) goto(`/albums/${r.id}`);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }
</script>

<div
  class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center"
  onclick={onclose}
>
  <div
    class="w-full max-w-md rounded-t-lg border border-slate-800 bg-slate-900 p-5 shadow-xl sm:rounded"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold">Nueva playlist</h2>
      <button
        onclick={onclose}
        class="grid size-8 place-items-center rounded text-slate-500 hover:bg-slate-800"
        aria-label="Cerrar"
      ><X size={18} /></button>
    </header>

    <form onsubmit={(e) => { e.preventDefault(); create(); }} class="space-y-3 text-sm">
      <label class="block">
        <span class="text-xs text-slate-400">Título</span>
        <input
          bind:value={title}
          required
          autofocus
          placeholder="Mi colección de verano"
          class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-slate-400">Artista <span class="text-slate-600">(opcional)</span></span>
        <input
          bind:value={artist}
          placeholder="Various Artists"
          class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-slate-400">Año <span class="text-slate-600">(opcional)</span></span>
        <input
          type="number"
          bind:value={year}
          min="1900"
          max="2100"
          placeholder="2026"
          class="mt-1 w-32 rounded border border-slate-800 bg-slate-950 px-2 py-1.5 focus:border-cyan-500 focus:outline-none"
        />
      </label>

      <p class="rounded border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-500">
        Una playlist es una colección a la que puedes añadir pistas de cualquier
        artista del catálogo. Queda guardada en tu biblioteca.
      </p>

      {#if error}
        <p class="rounded border border-red-900/50 bg-red-950/30 p-2 text-xs text-red-300">{error}</p>
      {/if}

      <div class="flex gap-2 pt-2">
        <button
          type="button"
          onclick={onclose}
          class="flex-1 rounded border border-slate-800 px-4 py-2 text-sm transition hover:bg-slate-800"
        >Cancelar</button>
        <button
          type="submit"
          disabled={saving || !title.trim()}
          class="flex-1 rounded bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
        >{saving ? 'Creando…' : 'Crear playlist'}</button>
      </div>
    </form>
  </div>
</div>
