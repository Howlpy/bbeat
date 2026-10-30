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
  class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center"
  onclick={onclose}
>
  <div
    class="w-full max-w-md rounded-t-xl border border-line bg-surface p-5 shadow-xl sm:rounded-xl"
    onclick={(e) => e.stopPropagation()}
    role="dialog"
  >
    <header class="mb-4 flex items-center justify-between">
      <h2 class="text-lg font-semibold">Nueva playlist</h2>
      <button
        onclick={onclose}
        class="grid size-10 place-items-center rounded-lg text-fg-subtle hover:bg-surface-2"
        aria-label="Cerrar"
      ><X size={18} /></button>
    </header>

    <form onsubmit={(e) => { e.preventDefault(); create(); }} class="space-y-3 text-sm">
      <label class="block">
        <span class="text-xs text-fg-muted">Título</span>
        <input
          bind:value={title}
          required
          autofocus
          placeholder="Mi colección de verano"
          class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-fg-muted">Artista <span class="text-fg-subtle">(opcional)</span></span>
        <input
          bind:value={artist}
          placeholder="Various Artists"
          class="mt-1 w-full rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-fg-muted">Año <span class="text-fg-subtle">(opcional)</span></span>
        <input
          type="number"
          bind:value={year}
          min="1900"
          max="2100"
          placeholder="2026"
          class="mt-1 w-32 rounded-lg border border-line bg-bg px-2 py-1.5 focus:border-accent focus:outline-none"
        />
      </label>

      <p class="rounded-lg border border-line bg-bg/60 px-3 py-2 text-xs text-fg-subtle min-h-11 sm:min-h-10">
        Una playlist es una colección a la que puedes añadir pistas de cualquier
        artista del catálogo. Queda guardada en tu biblioteca.
      </p>

      {#if error}
        <p class="rounded-lg border border-danger/40 bg-danger/10 p-2 text-xs text-danger">{error}</p>
      {/if}

      <div class="flex gap-2 pt-2">
        <button
          type="button"
          onclick={onclose}
          class="flex-1 rounded-lg border border-line px-4 py-2 text-sm transition hover:bg-surface-2 min-h-11 sm:min-h-10"
        >Cancelar</button>
        <button
          type="submit"
          disabled={saving || !title.trim()}
          class="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg transition hover:bg-accent-hover disabled:opacity-50 min-h-11 sm:min-h-10"
        >{saving ? 'Creando…' : 'Crear playlist'}</button>
      </div>
    </form>
  </div>
</div>
