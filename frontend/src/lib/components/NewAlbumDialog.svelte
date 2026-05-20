<script lang="ts">
  import { goto } from '$app/navigation';
  import { Globe, Lock, X } from 'lucide-svelte';
  import { api } from '$lib/api';

  let {
    onclose,
    oncreated
  }: { onclose: () => void; oncreated?: () => void } = $props();

  let title = $state('');
  let artist = $state('');
  let year = $state('');
  let isPublic = $state(false);
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
        is_public: isPublic
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
      <h2 class="text-lg font-semibold">Nuevo álbum</h2>
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

      <fieldset class="space-y-1">
        <legend class="mb-1 text-xs text-slate-400">Visibilidad</legend>
        <label class="flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm"
          class:border-cyan-500={!isPublic}
          class:bg-cyan-500={!isPublic}
          class:text-slate-950={!isPublic}
          class:border-slate-800={isPublic}>
          <input type="radio" bind:group={isPublic} value={false} class="sr-only" />
          <Lock size={14} /> Privado (solo tú)
        </label>
        <label class="flex cursor-pointer items-center gap-2 rounded border px-3 py-2 text-sm"
          class:border-cyan-500={isPublic}
          class:bg-cyan-500={isPublic}
          class:text-slate-950={isPublic}
          class:border-slate-800={!isPublic}>
          <input type="radio" bind:group={isPublic} value={true} class="sr-only" />
          <Globe size={14} /> Compartido (todos los users lo ven)
        </label>
      </fieldset>

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
        >{saving ? 'Creando…' : 'Crear álbum'}</button>
      </div>
    </form>
  </div>
</div>
