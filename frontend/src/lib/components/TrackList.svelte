<script lang="ts">
  import { onMount } from 'svelte';
  import { fly, fade } from 'svelte/transition';
  import {
    MoreVertical,
    Pencil,
    Trash2,
    Music2,
    Heart,
    ListPlus,
    CornerDownRight,
    Download,
    CircleCheck,
    Loader2,
    AlertCircle,
    Play,
    X
  } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';
  import { offline } from '$lib/offline.svelte';
  import { formatDuration, api, type Track, type Album } from '$lib/api';
  import EditTrackDialog from './EditTrackDialog.svelte';

  let {
    tracks = $bindable(),
    showAlbum = true,
    onchanged
  }: {
    tracks: Track[];
    showAlbum?: boolean;
    onchanged?: () => void;
  } = $props();

  let sheetTrack = $state<Track | null>(null);
  let sheetIndex = $state(0);
  let editing = $state<Track | null>(null);
  let albumsCache = $state<Album[]>([]);
  let poppedId = $state<number | null>(null);

  onMount(async () => {
    try {
      // Solo los álbumes/playlists que puedes mutar (para mover/añadir pistas).
      const r = await api.albums('mine');
      albumsCache = r.items;
    } catch {}
  });

  function openSheet(e: MouseEvent, t: Track, i: number) {
    e.stopPropagation();
    sheetTrack = t;
    sheetIndex = i;
  }
  function closeSheet() {
    sheetTrack = null;
  }

  function openEdit(track: Track) {
    editing = track;
    closeSheet();
  }

  async function toggleLike(e: MouseEvent, t: Track) {
    e.stopPropagation();
    const next = !t.liked;
    t.liked = next; // optimista
    if (next) {
      poppedId = t.id;
      setTimeout(() => poppedId === t.id && (poppedId = null), 380);
    }
    try {
      if (next) await api.likeTrack(t.id);
      else await api.unlikeTrack(t.id);
    } catch {
      t.liked = !next; // revertir si falla
    }
  }

  function playFromSheet() {
    if (sheetTrack) player.playTracks(tracks, sheetIndex);
    closeSheet();
  }
  function addToQueue(t: Track) {
    player.addToQueue(t);
    closeSheet();
  }
  function playNext(t: Track) {
    player.playNext(t);
    closeSheet();
  }
  function toggleDownload(t: Track) {
    if (offline.has(t.id)) offline.remove(t.id);
    else offline.download(t);
    closeSheet();
  }

  async function deleteTrack(t: Track) {
    closeSheet();
    if (!confirm(`¿Borrar "${t.title}"? Se eliminará el fichero del disco.`)) return;
    try {
      await api.deleteTrack(t.id);
      onchanged?.();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }
</script>

<ul class="divide-y divide-slate-900">
  {#each tracks as t, i (t.id)}
    {@const isCurrent = player.current?.id === t.id}
    <li>
      <div
        class="flex w-full items-center gap-3 px-2 py-2 text-left hover:bg-slate-900"
        class:bg-slate-900={isCurrent}
      >
        <button onclick={() => player.playTracks(tracks, i)} class="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span class="relative size-10 flex-none">
            {#if t.cover_url}
              <img src={t.cover_url} alt="" class="size-10 rounded object-cover" />
            {:else}
              <div class="grid size-10 place-items-center rounded bg-slate-800 text-slate-600">
                <Music2 size={14} />
              </div>
            {/if}
            {#if isCurrent && player.isPlaying}
              <span class="absolute inset-0 grid place-items-center rounded bg-black/45">
                <span class="flex h-3.5 items-end gap-[2px]">
                  <span class="eq-bar"></span>
                  <span class="eq-bar" style="animation-delay:.25s"></span>
                  <span class="eq-bar" style="animation-delay:.45s"></span>
                </span>
              </span>
            {/if}
          </span>
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm" class:text-cyan-400={isCurrent}>{t.title}</div>
            <div class="truncate text-xs text-slate-500">
              {t.artist_name}{#if showAlbum && t.album_title} · {t.album_title}{/if}
            </div>
          </div>
          <span class="flex-none font-mono text-xs text-slate-500">
            {formatDuration(t.duration_ms)}
          </span>
        </button>
        {#if offline.downloading.has(t.id)}
          <span class="flex-none text-cyan-400" title="Descargando…"><Loader2 size={14} class="animate-spin" /></span>
        {:else if offline.has(t.id)}
          <span class="flex-none text-cyan-500" title="Descargada"><CircleCheck size={14} /></span>
        {:else if offline.failed.has(t.id)}
          <button onclick={(e) => { e.stopPropagation(); offline.download(t); }} class="flex-none text-red-400" title="Falló — reintentar"><AlertCircle size={14} /></button>
        {/if}
        <button
          onclick={(e) => toggleLike(e, t)}
          class="grid size-8 flex-none place-items-center rounded transition hover:bg-slate-800"
          class:text-cyan-400={t.liked}
          class:text-slate-600={!t.liked}
          class:heart-pop={poppedId === t.id}
          aria-label={t.liked ? 'Quitar de me gusta' : 'Me gusta'}
          title={t.liked ? 'Quitar de me gusta' : 'Me gusta'}
        ><Heart size={16} fill={t.liked ? 'currentColor' : 'none'} /></button>
        <button
          onclick={(e) => openSheet(e, t, i)}
          class="grid size-8 flex-none place-items-center rounded text-slate-500 hover:bg-slate-800 hover:text-slate-200"
          aria-label="Más opciones"
        ><MoreVertical size={16} /></button>
      </div>
    </li>
  {/each}
</ul>

{#if sheetTrack}
  {@const t = sheetTrack}
  <button
    class="fixed inset-0 z-[60] cursor-default bg-black/60 backdrop-blur-sm"
    onclick={closeSheet}
    aria-label="Cerrar"
    transition:fade={{ duration: 150 }}
  ></button>
  <div
    class="fixed inset-x-0 bottom-0 z-[61] mx-auto max-w-2xl rounded-t-2xl border border-b-0 border-slate-700/60 bg-slate-900/95 pb-[env(safe-area-inset-bottom)] shadow-2xl shadow-black/50 backdrop-blur-xl"
    transition:fly={{ y: 420, duration: 280 }}
  >
    <div class="flex justify-center pt-2.5"><span class="h-1 w-10 rounded-full bg-slate-600"></span></div>
    <div class="flex items-center gap-3 px-4 py-3">
      {#if t.cover_url}
        <img src={t.cover_url} alt="" class="size-12 flex-none rounded object-cover" />
      {:else}
        <div class="grid size-12 flex-none place-items-center rounded bg-slate-800 text-slate-600"><Music2 size={18} /></div>
      {/if}
      <div class="min-w-0 flex-1">
        <div class="truncate text-sm font-medium">{t.title}</div>
        <div class="truncate text-xs text-slate-500">{t.artist_name}</div>
      </div>
      <button onclick={closeSheet} class="grid size-8 flex-none place-items-center rounded-full text-slate-400 hover:bg-slate-800" aria-label="Cerrar"><X size={18} /></button>
    </div>
    <div class="border-t border-slate-800/70 py-1 text-sm">
      <button onclick={playFromSheet} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800"><Play size={17} /> Reproducir</button>
      <button onclick={() => addToQueue(t)} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800"><ListPlus size={17} /> Añadir a la cola</button>
      <button onclick={() => playNext(t)} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800"><CornerDownRight size={17} /> Reproducir a continuación</button>
      <button onclick={(e) => { toggleLike(e, t); closeSheet(); }} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800">
        <Heart size={17} class={t.liked ? 'text-cyan-400' : ''} fill={t.liked ? 'currentColor' : 'none'} /> {t.liked ? 'Quitar de me gusta' : 'Me gusta'}
      </button>
      <button onclick={() => toggleDownload(t)} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800">
        {#if offline.downloading.has(t.id)}
          <Loader2 size={17} class="animate-spin" /> Descargando…
        {:else if offline.has(t.id)}
          <CircleCheck size={17} class="text-cyan-400" /> Quitar descarga
        {:else if offline.failed.has(t.id)}
          <AlertCircle size={17} class="text-red-400" /> Reintentar descarga
        {:else}
          <Download size={17} /> Descargar
        {/if}
      </button>
      {#if offline.failed.has(t.id) && offline.lastError}
        <p class="px-4 pb-2 text-xs text-red-400/80">Error: {offline.lastError}</p>
      {/if}
      <div class="my-1 border-t border-slate-800/70"></div>
      <button onclick={() => openEdit(t)} class="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-slate-800"><Pencil size={17} /> Editar</button>
      <button onclick={() => deleteTrack(t)} class="flex w-full items-center gap-3 px-4 py-2.5 text-left text-red-400 hover:bg-slate-800"><Trash2 size={17} /> Borrar</button>
    </div>
  </div>
{/if}

{#if editing}
  <EditTrackDialog
    track={editing}
    albums={albumsCache}
    onclose={() => (editing = null)}
    onsaved={() => onchanged?.()}
  />
{/if}
