<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import {
    AlertTriangle,
    Camera,
    Disc3,
    Globe,
    Loader2,
    Lock,
    Pencil,
    Play,
    Trash2
  } from 'lucide-svelte';
  import { api, type Track, type Album } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';
  import { player } from '$lib/player.svelte';

  const albumId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let album = $state<Album | null>(null);
  let error = $state<string | null>(null);
  let coverInput = $state<HTMLInputElement | null>(null);
  let uploading = $state(false);
  let coverMsg = $state<string | null>(null);
  let coverNonce = $state(0);
  let editing = $state(false);
  let editTitle = $state('');
  let editYear = $state('');
  let savingEdit = $state(false);

  async function load() {
    try {
      const [trackRes, albumsRes] = await Promise.all([
        api.tracks({ album_id: albumId, limit: 500 }),
        api.albums()
      ]);
      tracks = trackRes.items;
      album = albumsRes.items.find((a) => a.id === albumId) ?? null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(load);

  function playAll() {
    if (tracks.length) player.playTracks(tracks, 0);
  }

  function startEdit() {
    if (!album) return;
    editTitle = album.title;
    editYear = album.year ? String(album.year) : '';
    editing = true;
  }

  async function saveEdit() {
    if (!album) return;
    savingEdit = true;
    try {
      await api.editAlbum(album.id, {
        title: editTitle.trim() || undefined,
        year: editYear ? Number(editYear) : undefined
      });
      editing = false;
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      savingEdit = false;
    }
  }

  async function togglePublic() {
    if (!album) return;
    try {
      await api.editAlbum(album.id, { is_public: !album.is_public });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteAlbum() {
    if (!album) return;
    if (
      !confirm(
        `¿Borrar el álbum "${album.title}" y sus ${album.track_count} pistas? Se eliminan los ficheros del disco.`
      )
    )
      return;
    try {
      await api.deleteAlbum(album.id);
      goto('/albums');
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function onCoverUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !album) return;
    uploading = true;
    coverMsg = null;
    try {
      const r = await api.uploadAlbumCover(album.id, file);
      coverMsg = `Carátula actualizada en ${r.tracks_updated} ${r.tracks_updated === 1 ? 'pista' : 'pistas'}.`;
      coverNonce++;
      await load();
    } catch (err) {
      coverMsg = err instanceof Error ? err.message : String(err);
    } finally {
      uploading = false;
      if (coverInput) coverInput.value = '';
    }
  }
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  {#if error}
    <p class="inline-flex items-center gap-2 text-red-400">
      <AlertTriangle size={16} /> {error}
    </p>
  {:else if album}
    <div class="mb-6 flex flex-col items-start gap-4 sm:flex-row sm:items-end">
      <div class="relative flex-none">
        {#if album.cover_url}
          <img
            src="{album.cover_url}{album.cover_url.includes('?') ? '&' : '?'}v={coverNonce}"
            alt=""
            class="size-40 rounded object-cover shadow-xl shadow-cyan-500/10"
          />
        {:else}
          <div class="grid size-40 place-items-center rounded bg-slate-800 text-slate-700">
            <Disc3 size={56} />
          </div>
        {/if}
        <label
          class="absolute bottom-1 right-1 flex cursor-pointer items-center gap-1 rounded-full bg-slate-900/90 px-2 py-1 text-xs text-slate-200 backdrop-blur transition hover:bg-slate-800"
          title="Cambiar carátula"
        >
          <input
            bind:this={coverInput}
            type="file"
            accept="image/jpeg,image/png"
            class="hidden"
            onchange={onCoverUpload}
            disabled={uploading}
          />
          {#if uploading}
            <Loader2 size={14} class="animate-spin" />
          {:else}
            <Camera size={14} />
          {/if}
        </label>
      </div>
      <div class="min-w-0 flex-1">
        {#if !editing}
          <h1 class="flex flex-wrap items-center gap-2 text-2xl font-bold">
            {album.title}
            {#if album.is_public}
              <span
                class="inline-flex items-center gap-1 rounded border border-cyan-700/40 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-cyan-300"
                title="Visible para todos los usuarios"
              ><Globe size={10} /> compartido</span>
            {:else if album.is_mine}
              <span
                class="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-400"
                title="Solo tú"
              ><Lock size={10} /> privado</span>
            {/if}
          </h1>
          <div class="text-sm text-slate-400">
            {album.artist_name}{#if album.year} · {album.year}{/if} · {album.track_count}
            {album.track_count === 1 ? 'pista' : 'pistas'}
          </div>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <button
              onclick={playAll}
              disabled={tracks.length === 0}
              class="inline-flex items-center gap-1.5 rounded bg-cyan-400 px-4 py-1.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
            >
              <Play size={14} fill="currentColor" /> Reproducir
            </button>
            {#if album.is_mine}
              <button
                onclick={togglePublic}
                class="inline-flex items-center gap-1.5 rounded border border-slate-800 px-3 py-1.5 text-sm transition hover:bg-slate-800"
                title={album.is_public ? 'Hacer privado' : 'Compartir con otros'}
              >
                {#if album.is_public}
                  <Lock size={14} /> Hacer privado
                {:else}
                  <Globe size={14} /> Compartir
                {/if}
              </button>
              <button
                onclick={startEdit}
                class="inline-flex items-center gap-1.5 rounded border border-slate-800 px-3 py-1.5 text-sm transition hover:bg-slate-800"
              ><Pencil size={14} /> Editar</button>
              <button
                onclick={deleteAlbum}
                class="inline-flex items-center gap-1.5 rounded border border-red-900/50 px-3 py-1.5 text-sm text-red-300 transition hover:bg-red-950/40"
              ><Trash2 size={14} /> Borrar</button>
            {/if}
          </div>
        {:else}
          <div class="space-y-2">
            <label class="block">
              <span class="text-xs text-slate-400">Título</span>
              <input
                bind:value={editTitle}
                class="mt-1 w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
              />
            </label>
            <label class="block">
              <span class="text-xs text-slate-400">Año</span>
              <input
                type="number"
                bind:value={editYear}
                min="1900"
                max="2100"
                class="mt-1 w-32 rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-sm focus:border-cyan-500 focus:outline-none"
              />
            </label>
            <div class="flex gap-2">
              <button
                onclick={() => (editing = false)}
                class="rounded border border-slate-800 px-3 py-1.5 text-sm transition hover:bg-slate-800"
              >Cancelar</button>
              <button
                onclick={saveEdit}
                disabled={savingEdit}
                class="rounded bg-cyan-400 px-4 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
              >{savingEdit ? 'Guardando…' : 'Guardar'}</button>
            </div>
          </div>
        {/if}
        {#if coverMsg}
          <p class="mt-2 text-xs text-cyan-400">{coverMsg}</p>
        {/if}
      </div>
    </div>

    {#if tracks.length === 0}
      <p class="rounded border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">
        Este álbum está vacío. Importa pistas desde
        <a href="/import" class="text-cyan-400 underline">/import</a>
        y selecciona "{album.title}" como destino.
      </p>
    {:else}
      <TrackList bind:tracks showAlbum={false} onchanged={load} />
    {/if}
  {:else}
    <p class="text-slate-500">Cargando…</p>
  {/if}
</div>
