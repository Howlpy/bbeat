<script lang="ts">
  import { onMount } from 'svelte';
  import { MoreVertical, Pencil, Trash2, Music2, Heart } from 'lucide-svelte';
  import { player } from '$lib/player.svelte';
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

  let menuFor = $state<number | null>(null);
  let editing = $state<Track | null>(null);
  let albumsCache = $state<Album[]>([]);

  onMount(async () => {
    try {
      const r = await api.albums();
      albumsCache = r.items;
    } catch {}
  });

  function play(i: number) {
    if (menuFor !== null) {
      menuFor = null;
      return;
    }
    player.playTracks(tracks, i);
  }

  function toggleMenu(e: MouseEvent, id: number) {
    e.stopPropagation();
    menuFor = menuFor === id ? null : id;
  }

  function openEdit(track: Track) {
    editing = track;
    menuFor = null;
  }

  async function toggleLike(e: MouseEvent, t: Track) {
    e.stopPropagation();
    const next = !t.liked;
    t.liked = next; // optimista
    try {
      if (next) await api.likeTrack(t.id);
      else await api.unlikeTrack(t.id);
    } catch {
      t.liked = !next; // revertir si falla
    }
  }

  async function deleteTrack(t: Track) {
    menuFor = null;
    if (!confirm(`¿Borrar "${t.title}"? Se eliminará el fichero del disco.`)) return;
    try {
      await api.deleteTrack(t.id);
      onchanged?.();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }
</script>

<svelte:window onclick={() => (menuFor = null)} />

<ul class="divide-y divide-slate-900">
  {#each tracks as t, i (t.id)}
    {@const isCurrent = player.current?.id === t.id}
    <li>
      <div
        class="flex w-full items-center gap-3 px-2 py-2 text-left hover:bg-slate-900"
        class:bg-slate-900={isCurrent}
      >
        <button onclick={() => play(i)} class="flex min-w-0 flex-1 items-center gap-3 text-left">
          {#if t.cover_url}
            <img src={t.cover_url} alt="" class="size-10 flex-none rounded object-cover" />
          {:else}
            <div class="grid size-10 flex-none place-items-center rounded bg-slate-800 text-slate-600">
              <Music2 size={14} />
            </div>
          {/if}
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
        <button
          onclick={(e) => toggleLike(e, t)}
          class="grid size-8 flex-none place-items-center rounded transition hover:bg-slate-800"
          class:text-cyan-400={t.liked}
          class:text-slate-600={!t.liked}
          aria-label={t.liked ? 'Quitar de me gusta' : 'Me gusta'}
          title={t.liked ? 'Quitar de me gusta' : 'Me gusta'}
        ><Heart size={16} fill={t.liked ? 'currentColor' : 'none'} /></button>
        <div class="relative">
          <button
            onclick={(e) => toggleMenu(e, t.id)}
            class="grid size-8 flex-none place-items-center rounded text-slate-500 hover:bg-slate-800 hover:text-slate-200"
            aria-label="Más opciones"
          ><MoreVertical size={16} /></button>
          {#if menuFor === t.id}
            <div
              class="absolute right-0 top-9 z-20 w-40 overflow-hidden rounded border border-slate-800 bg-slate-900 text-sm shadow-xl"
              onclick={(e) => e.stopPropagation()}
              role="menu"
            >
              <button
                onclick={() => openEdit(t)}
                class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-800"
              ><Pencil size={14} /> Editar</button>
              <button
                onclick={() => deleteTrack(t)}
                class="flex w-full items-center gap-2 px-3 py-2 text-left text-red-400 hover:bg-slate-800"
              ><Trash2 size={14} /> Borrar</button>
            </div>
          {/if}
        </div>
      </div>
    </li>
  {/each}
</ul>

{#if editing}
  <EditTrackDialog
    track={editing}
    albums={albumsCache}
    onclose={() => (editing = null)}
    onsaved={() => onchanged?.()}
  />
{/if}
