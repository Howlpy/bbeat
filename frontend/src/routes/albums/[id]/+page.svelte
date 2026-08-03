<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import {
    AlertTriangle,
    ArrowLeft,
    ArrowUpDown,
    Bookmark,
    BookmarkCheck,
    Camera,
    Disc3,
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
  import AddTracksDialog from '$lib/components/AddTracksDialog.svelte';
  import DownloadAllButton from '$lib/components/DownloadAllButton.svelte';
  import { player } from '$lib/player.svelte';

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

  let savingSave = $state(false);
  type PlaylistSort = "original" | "title-asc" | "title-desc" | "artist" | "album" | "genre" | "duration-asc" | "duration-desc";
  let playlistQuery = $state("");
  let playlistSort = $state<PlaylistSort>("original");
  const collator = new Intl.Collator("es", { numeric: true, sensitivity: "base" });

  function compareOptionalText(a: string | null | undefined, b: string | null | undefined) {
    const av = a?.trim() ?? "";
    const bv = b?.trim() ?? "";
    if (!av && bv) return 1;
    if (av && !bv) return -1;
    return collator.compare(av, bv);
  }

  function trackMatches(track: Track, query: string) {
    if (!query) return true;
    return [track.title, track.artist_name, track.album_title, track.genre]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase("es").includes(query));
  }

  const visibleTracks = $derived.by<Track[]>(() => {
    if (album?.kind !== "playlist") return tracks;
    const query = playlistQuery.trim().toLocaleLowerCase("es");
    const filtered = tracks.filter((track) => trackMatches(track, query));
    if (playlistSort === "original") return filtered;

    return [...filtered].sort((a, b) => {
      let compared = 0;
      switch (playlistSort) {
        case "title-asc":
          compared = collator.compare(a.title, b.title);
          break;
        case "title-desc":
          compared = collator.compare(b.title, a.title);
          break;
        case "artist":
          compared = collator.compare(a.artist_name, b.artist_name);
          break;
        case "album":
          compared = compareOptionalText(a.album_title, b.album_title);
          break;
        case "genre":
          compared = compareOptionalText(a.genre, b.genre);
          break;
        case "duration-asc":
        case "duration-desc": {
          const ad = a.duration_ms;
          const bd = b.duration_ms;
          if (ad == null && bd != null) compared = 1;
          else if (ad != null && bd == null) compared = -1;
          else if (ad != null && bd != null) {
            compared = playlistSort === "duration-asc" ? ad - bd : bd - ad;
          }
          break;
        }
      }
      return compared || collator.compare(a.title, b.title);
    });
  });

  async function load() {
    try {
      const [trackRes, albumRes] = await Promise.all([
        api.tracks({ album_id: albumId, limit: 500 }),
        api.album(albumId)
      ]);
      tracks = trackRes.items;
      album = albumRes;
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

  onMount(load);

  function playAll() {
    if (visibleTracks.length) player.playTracks(visibleTracks, 0);
  }

  function goBack() {
    if (typeof window !== "undefined" && window.history.length > 1) {
      window.history.back();
    } else {
      goto("/albums");
    }
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

<div class="mx-auto max-w-3xl px-4 pt-6">
  <button
    onclick={goBack}
    class="mb-4 inline-flex items-center gap-1.5 rounded px-2 py-1.5 text-sm text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
    aria-label="Volver"
  >
    <ArrowLeft size={17} /> Volver
  </button>
  {#if error}
    <p class="inline-flex items-center gap-2 text-red-400">
      <AlertTriangle size={16} /> {error}
    </p>
  {:else if album}
    {#if album.cover_url}
      <div class="pointer-events-none fixed inset-x-0 top-0 -z-10 h-80 overflow-hidden">
        <img loading="lazy" decoding="async"
          src={album.cover_url}
          alt=""
          class="size-full scale-125 object-cover opacity-25 blur-2xl"
        />
        <div class="absolute inset-0 bg-gradient-to-b from-transparent to-slate-950"></div>
      </div>
    {/if}
    <div class="mb-6 flex flex-col items-start gap-4 sm:flex-row sm:items-end">
      <div class="relative flex-none">
        {#if album.cover_url}
          <img loading="lazy" decoding="async"
            src={album.cover_url}
            alt=""
            class="size-40 rounded object-cover shadow-xl shadow-cyan-500/10"
          />
        {:else}
          <div class="grid size-40 place-items-center rounded bg-slate-800 text-slate-700">
            <Disc3 size={56} />
          </div>
        {/if}
        {#if album.is_mine}
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
        {/if}
      </div>
      <div class="min-w-0 flex-1">
        {#if !editing}
          <h1 class="flex flex-wrap items-center gap-2 text-2xl font-bold">
            {album.title}
            {#if album.kind === 'playlist'}
              <span
                class="inline-flex items-center gap-1 rounded border border-cyan-700/40 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-cyan-300"
                title="Colección multi-artista"
              ><ListMusic size={10} /> playlist</span>
            {/if}
          </h1>
          <div class="text-sm text-slate-400">
            {album.artist_name}{#if album.year} · {album.year}{/if} · {album.track_count}
            {album.track_count === 1 ? 'pista' : 'pistas'}
          </div>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <button
              onclick={playAll}
              disabled={visibleTracks.length === 0}
              class="inline-flex items-center gap-1.5 rounded bg-cyan-400 px-4 py-1.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
            >
              <Play size={14} fill="currentColor" /> Reproducir
            </button>
            <DownloadAllButton {tracks} label="Descargar" class="rounded border border-slate-800 px-3 py-1.5" />
            <button
              onclick={toggleSave}
              disabled={savingSave}
              class="inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm transition disabled:opacity-50 {album.is_saved
                ? 'border-cyan-700/40 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20'
                : 'border-slate-800 hover:bg-slate-800'}"
              title={album.is_saved ? 'Quitar de tu biblioteca' : 'Guardar en tu biblioteca'}
            >
              {#if album.is_saved}
                <BookmarkCheck size={14} /> Guardado
              {:else}
                <Bookmark size={14} /> Guardar
              {/if}
            </button>
            {#if album.is_mine}
              <button
                onclick={() => (addingTracks = true)}
                class="inline-flex items-center gap-1.5 rounded border border-cyan-700/40 bg-cyan-500/10 px-3 py-1.5 text-sm text-cyan-300 transition hover:bg-cyan-500/20"
              ><Plus size={14} /> Añadir pistas</button>
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

    {#if album.kind === "playlist" && tracks.length > 0}
      <div class="mb-3 flex flex-col gap-2 sm:flex-row">
        <div class="flex min-w-0 flex-1 items-center gap-2 rounded border border-slate-800 bg-slate-900 px-3 py-2">
          <Search size={16} class="flex-none text-slate-500" />
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
              class="grid size-6 flex-none place-items-center rounded text-slate-500 hover:bg-slate-800 hover:text-slate-200"
              aria-label="Borrar búsqueda"
            ><X size={14} /></button>
          {/if}
        </div>
        <label class="flex items-center gap-2 rounded border border-slate-800 bg-slate-900 px-3 py-2 text-sm">
          <ArrowUpDown size={15} class="text-slate-500" />
          <span class="sr-only">Ordenar playlist</span>
          <select bind:value={playlistSort} class="bg-transparent text-sm focus:outline-none">
            <option value="original">Orden original</option>
            <option value="title-asc">Título A–Z</option>
            <option value="title-desc">Título Z–A</option>
            <option value="artist">Artista</option>
            <option value="album">Álbum</option>
            <option value="genre">Género</option>
            <option value="duration-asc">Duración: menor</option>
            <option value="duration-desc">Duración: mayor</option>
          </select>
        </label>
      </div>
      <p class="mb-1 px-2 text-[11px] text-slate-600">
        {visibleTracks.length === tracks.length ? tracks.length + " pistas" : visibleTracks.length + " de " + tracks.length + " pistas"}
      </p>
    {/if}

    {#if tracks.length === 0}
      <div class="rounded border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">
        {#if album.kind === "playlist"}
          <p>Esta playlist está vacía.</p>
        {:else}
          <p>Este álbum está vacío.</p>
        {/if}
        <div class="mt-3 flex flex-wrap justify-center gap-2">
          {#if album.is_mine}
            <button
              onclick={() => (addingTracks = true)}
              class="inline-flex items-center gap-1.5 rounded bg-cyan-400 px-3 py-1.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
            ><Plus size={14} /> Añadir pistas existentes</button>
          {/if}
          <a
            href="/import"
            class="inline-flex items-center gap-1.5 rounded border border-slate-800 px-3 py-1.5 text-sm transition hover:bg-slate-800"
          >Importar nuevas</a>
        </div>
      </div>
    {:else if visibleTracks.length === 0}
      <div class="rounded border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">
        <p>No hay pistas que coincidan con “{playlistQuery}”.</p>
        <button onclick={() => (playlistQuery = "")} class="mt-2 text-cyan-400 hover:underline">Limpiar búsqueda</button>
      </div>
    {:else}
      <TrackList
        tracks={visibleTracks}
        showAlbum={album.kind === "playlist" && playlistSort === "album"}
        showGenre={album.kind === "playlist" && playlistSort === "genre"}
        onchanged={load}
      />
    {/if}
  {:else}
    <p class="text-slate-500">Cargando…</p>
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
