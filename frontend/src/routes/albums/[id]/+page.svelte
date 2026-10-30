<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { onReconnect } from '$lib/net.svelte';
  import ErrorState from '$lib/components/ErrorState.svelte';
  import { page } from '$app/state';
  import {
    Bookmark,
    BookmarkCheck,
    Camera,
    Disc3,
    EllipsisVertical,
    ListMusic,
    Loader2,
    Pencil,
    Play,
    Plus,
    Search,
    Trash2,
    X
  } from 'lucide-svelte';
  import { api, type Track, type Album } from '$lib/api';
  import TrackList from '$lib/components/TrackList.svelte';
  import SortSelect from '$lib/components/SortSelect.svelte';
  import { sortTracks, trackMatches, type TrackSort } from '$lib/sort';
  import { pushBack } from '$lib/backstack.svelte';
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import AddTracksDialog from '$lib/components/AddTracksDialog.svelte';
  import DownloadAllButton from '$lib/components/DownloadAllButton.svelte';
  import DownloadZipButton from '$lib/components/DownloadZipButton.svelte';
  import { player } from '$lib/player.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import EmptyState from '$lib/components/ui/EmptyState.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';

  const albumId = $derived(Number(page.params.id));

  let tracks = $state<Track[]>([]);
  let album = $state<Album | null>(null);
  let error = $state<string | null>(null);
  let coverInput = $state<HTMLInputElement | null>(null);
  let uploading = $state(false);
  let coverMsg = $state<string | null>(null);
  let editing = $state(false);
  let editTitle = $state('');
  let editYear = $state('');
  let savingEdit = $state(false);
  let addingTracks = $state(false);
  let menuOpen = $state(false);
  let menuEl = $state<HTMLDivElement | null>(null);

  // Atrás de Android: cierra el menú ⋯ y sale del modo edición.
  $effect(() => {
    if (menuOpen) return pushBack(() => (menuOpen = false));
  });
  $effect(() => {
    if (editing) return pushBack(() => (editing = false));
  });

  // Cierra el menú ⋯ al tocar fuera
  $effect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (menuEl && !menuEl.contains(e.target as Node)) menuOpen = false;
    };
    document.addEventListener('click', onDoc, true);
    return () => document.removeEventListener('click', onDoc, true);
  });

  let savingSave = $state(false);
  let playlistQuery = $state("");
  let playlistSort = $state<TrackSort>("original");

  const isPlaylist = $derived(album?.kind === "playlist");
  // La búsqueda solo tiene sentido en playlists (un álbum cabe de un vistazo);
  // la ordenación vale para las dos y se recuerda por lista.
  const visibleTracks = $derived.by<Track[]>(() => {
    const query = isPlaylist ? playlistQuery.trim().toLocaleLowerCase("es") : "";
    const filtered = query ? tracks.filter((track) => trackMatches(track, query)) : tracks;
    return sortTracks(filtered, playlistSort);
  });

  async function load() {
    try {
      const [trackRes, albumRes] = await Promise.all([
        api.tracks({ album_id: albumId, limit: 500 }),
        api.album(albumId)
      ]);
      tracks = trackRes.items;
      album = albumRes;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  }

  async function toggleSave() {
    if (!album || savingSave) return;
    savingSave = true;
    const next = !album.is_saved;
    album.is_saved = next; // optimista
    try {
      if (next) await api.saveAlbum(album.id);
      else await api.unsaveAlbum(album.id);
    } catch (e) {
      album.is_saved = !next;
      alert(e instanceof Error ? e.message : String(e));
    } finally {
      savingSave = false;
    }
  }

  onMount(() => {
    load();
    return onReconnect(() => {
      if (error) load();
    });
  });

  function playAll() {
    if (visibleTracks.length) player.playTracks(visibleTracks, 0);
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
      await load();
    } catch (err) {
      coverMsg = err instanceof Error ? err.message : String(err);
    } finally {
      uploading = false;
      if (coverInput) coverInput.value = '';
    }
  }
</script>

<div class="page-narrow">
  <BackButton fallback="/albums" />
  {#if error}
    <ErrorState {error} />
  {:else if album}
    <div class="mb-8 flex flex-col items-start gap-5 sm:flex-row sm:items-end">
      <div class="relative flex-none">
        {#if album.cover_url}
          <img loading="lazy" decoding="async"
            src={album.cover_url}
            alt=""
            class="size-40 rounded-xl object-cover sm:size-48"
          />
        {:else}
          <div class="grid size-40 place-items-center rounded-xl bg-surface-2 text-fg-subtle sm:size-48">
            <Disc3 size={56} />
          </div>
        {/if}
        {#if album.is_mine}
          <label
            class="absolute bottom-2 right-2 grid size-10 cursor-pointer place-items-center rounded-full bg-surface-2 text-fg transition hover:bg-surface-3"
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
        {/if}
      </div>
      <div class="min-w-0 flex-1">
        {#if !editing}
          <h1 class="flex flex-wrap items-center gap-2 text-2xl font-bold tracking-tight sm:text-3xl">
            {album.title}
            {#if album.kind === 'playlist'}
              <span
                class="inline-flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-2 py-0.5 text-xs font-medium uppercase tracking-wider text-accent"
                title="Colección multi-artista"
              ><ListMusic size={10} /> playlist</span>
            {/if}
          </h1>
          <div class="mt-1 text-sm text-fg-muted">
            {album.artist_name}{#if album.year} · {album.year}{/if} · {album.track_count}
            {album.track_count === 1 ? 'pista' : 'pistas'}
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-2">
            <Button variant="primary" onclick={playAll} disabled={visibleTracks.length === 0}>
              <Play size={16} fill="currentColor" /> Reproducir
            </Button>
            <Button
              onclick={toggleSave}
              disabled={savingSave}
              class={album.is_saved ? 'border-accent/40 text-accent' : ''}
              title={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
            >
              {#if album.is_saved}
                <BookmarkCheck size={16} /> Guardado
              {:else}
                <Bookmark size={16} /> Guardar
              {/if}
            </Button>
            <div class="relative" bind:this={menuEl}>
              <Button
                icon
                onclick={() => (menuOpen = !menuOpen)}
                aria-label="Más acciones"
                aria-expanded={menuOpen}
              ><EllipsisVertical size={18} /></Button>
              {#if menuOpen}
                <div
                  class="absolute right-0 top-full z-30 mt-2 w-60 overflow-hidden rounded-xl border border-line bg-surface-2 py-1 shadow-xl"
                  role="menu"
                >
                  <DownloadAllButton {tracks} label="Guardar offline" class="flex min-h-11 w-full px-4 hover:bg-surface-3" />
                  <DownloadZipButton
                    albumId={albumId}
                    count={tracks.length}
                    label="Exportar .zip"
                    class="flex min-h-11 w-full gap-2 px-4 hover:bg-surface-3"
                  />
                  {#if album.is_mine}
                    <button
                      onclick={() => { menuOpen = false; addingTracks = true; }}
                      class="flex min-h-11 w-full items-center gap-2 px-4 text-left text-sm font-medium hover:bg-surface-3"
                    ><Plus size={16} /> Añadir pistas</button>
                    <button
                      onclick={() => { menuOpen = false; startEdit(); }}
                      class="flex min-h-11 w-full items-center gap-2 px-4 text-left text-sm font-medium hover:bg-surface-3"
                    ><Pencil size={16} /> Editar</button>
                    <div class="my-1 border-t border-line"></div>
                    <button
                      onclick={() => { menuOpen = false; deleteAlbum(); }}
                      class="flex min-h-11 w-full items-center gap-2 px-4 text-left text-sm font-medium text-danger hover:bg-danger/10"
                    ><Trash2 size={16} /> Eliminar</button>
                  {/if}
                </div>
              {/if}
            </div>
          </div>
        {:else}
          <div class="space-y-2">
            <label class="block">
              <span class="text-xs text-fg-muted">Título</span>
              <input
                bind:value={editTitle}
                class="mt-1 min-h-11 w-full rounded-lg border border-line bg-bg px-3 text-sm focus:border-accent focus:outline-none"
              />
            </label>
            <label class="block">
              <span class="text-xs text-fg-muted">Año</span>
              <input
                type="number"
                bind:value={editYear}
                min="1900"
                max="2100"
                class="mt-1 min-h-11 w-32 rounded-lg border border-line bg-bg px-3 text-sm focus:border-accent focus:outline-none"
              />
            </label>
            <div class="flex gap-2 pt-1">
              <Button onclick={() => (editing = false)}>Cancelar</Button>
              <Button variant="primary" onclick={saveEdit} disabled={savingEdit}>{savingEdit ? 'Guardando…' : 'Guardar'}</Button>
            </div>
          </div>
        {/if}
        {#if coverMsg}
          <p class="mt-2 text-xs text-accent">{coverMsg}</p>
        {/if}
      </div>
    </div>

    {#if tracks.length > 0}
      <div class="mb-3 flex flex-col gap-2 sm:flex-row">
        {#if isPlaylist}
        <div class="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-3">
          <Search size={16} class="flex-none text-fg-subtle" />
          <input
            type="search"
            bind:value={playlistQuery}
            placeholder="Buscar en esta playlist…"
            aria-label="Buscar en esta playlist"
            class="min-w-0 flex-1 bg-transparent text-sm focus:outline-none"
          />
          {#if playlistQuery}
            <button
              type="button"
              onclick={() => (playlistQuery = "")}
              class="grid size-10 flex-none place-items-center rounded-lg text-fg-subtle hover:bg-surface-2 hover:text-fg"
              aria-label="Borrar búsqueda"
            ><X size={14} /></button>
          {/if}
        </div>
        {:else}
          <div class="min-w-0 flex-1"></div>
        {/if}
        <SortSelect
          prefKey="sort:album:{albumId}"
          bind:value={playlistSort}
          originalLabel={isPlaylist ? "Orden de la playlist" : "Orden del álbum"}
        />
      </div>
      <p class="mb-1 px-2 text-xs text-fg-subtle">
        {visibleTracks.length === tracks.length ? tracks.length + " pistas" : visibleTracks.length + " de " + tracks.length + " pistas"}
      </p>
    {/if}

    {#if tracks.length === 0}
      <EmptyState icon={album.kind === 'playlist' ? ListMusic : Disc3} title={album.kind === 'playlist' ? 'Esta playlist está vacía' : 'Este álbum está vacío'}>
        {#if album.is_mine}
          <Button variant="primary" onclick={() => (addingTracks = true)}><Plus size={16} /> Añadir pistas existentes</Button>
        {/if}
        <Button href="/import">Importar nuevas</Button>
      </EmptyState>
    {:else if visibleTracks.length === 0}
      <div class="rounded-xl border border-dashed border-line p-8 text-center text-sm text-fg-muted">
        <p>No hay pistas que coincidan con “{playlistQuery}”.</p>
        <button onclick={() => (playlistQuery = "")} class="mt-2 text-accent hover:underline">Limpiar búsqueda</button>
      </div>
    {:else}
      <TrackList
        tracks={visibleTracks}
        showAlbum={isPlaylist && playlistSort === "album"}
        showGenre={playlistSort === "genre"}
        onchanged={load}
      />
    {/if}
  {:else}
    <div class="flex items-end gap-5">
      <Skeleton class="size-40 flex-none sm:size-48" />
      <div class="flex-1 space-y-3"><Skeleton class="h-8 w-2/3" /><Skeleton class="h-4 w-1/3" /></div>
    </div>
    <div class="mt-8 space-y-2">
      {#each Array(6) as _}<Skeleton class="h-14 w-full" />{/each}
    </div>
  {/if}
</div>

{#if addingTracks && album}
  <AddTracksDialog
    albumId={album.id}
    excludeIds={tracks.map((t) => t.id)}
    onclose={() => (addingTracks = false)}
    onadded={() => load()}
  />
{/if}
