<script lang="ts">
  import { Check, Clock, FolderOpen, Loader2, X } from 'lucide-svelte';
  import { api, type Album, formatBytes } from '$lib/api';

  let { albums = [], onuploaded }: { albums?: Album[]; onuploaded?: () => void } = $props();

  type Item = {
    file: File;
    title: string;
    status: 'pending' | 'uploading' | 'done' | 'failed';
    error?: string;
  };

  let items = $state<Item[]>([]);
  let dragOver = $state(false);
  let mode = $state<'single' | 'new' | 'existing'>('single');
  let albumOv = $state('');
  let artistOv = $state('');
  let yearOv = $state('');
  let targetAlbumId = $state<number | null>(null);
  let uploading = $state(false);

  const AUDIO_EXT_RE = /\.(mp3|flac|ogg|opus|m4a|aac|wav)$/i;

  function cleanName(name: string): string {
    return name.replace(/\.[^.]+$/, '').replace(/_/g, ' ').trim();
  }

  function addFiles(list: FileList | File[]) {
    const arr = Array.from(list).filter((f) => AUDIO_EXT_RE.test(f.name));
    items = [
      ...items,
      ...arr.map((file) => ({ file, title: cleanName(file.name), status: 'pending' as const }))
    ];
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    dragOver = false;
    if (e.dataTransfer?.files) addFiles(e.dataTransfer.files);
  }

  function onPick(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files) addFiles(input.files);
    input.value = '';
  }

  function removeItem(i: number) {
    items = items.filter((_, idx) => idx !== i);
  }

  async function uploadAll() {
    if (uploading || !items.length) return;
    uploading = true;
    const opts: Parameters<typeof api.uploadTrack>[1] = {};
    if (mode === 'single') {
      opts.as_single = true;
      if (artistOv.trim()) opts.artist = artistOv.trim();
      if (yearOv.trim()) opts.year = Number(yearOv) || undefined;
    } else if (mode === 'existing' && targetAlbumId) {
      opts.target_album_id = targetAlbumId;
    } else if (mode === 'new') {
      if (albumOv.trim()) opts.album = albumOv.trim();
      if (artistOv.trim()) opts.artist = artistOv.trim();
      if (yearOv.trim()) opts.year = Number(yearOv) || undefined;
    }
    for (let i = 0; i < items.length; i++) {
      if (items[i].status === 'done') continue;
      items[i] = { ...items[i], status: 'uploading' };
      try {
        await api.uploadTrack(items[i].file, { ...opts, title: items[i].title?.trim() || undefined });
        items[i] = { ...items[i], status: 'done' };
      } catch (e) {
        items[i] = {
          ...items[i],
          status: 'failed',
          error: e instanceof Error ? e.message : String(e)
        };
      }
    }
    uploading = false;
    onuploaded?.();
  }

  function clearDone() {
    items = items.filter((i) => i.status !== 'done');
  }
</script>

<div class="space-y-3">
  <label
    role="button"
    class="block cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition"
    class:border-cyan-500={dragOver}
    class:bg-cyan-500={dragOver}
    class:bg-opacity-5={dragOver}
    class:border-slate-800={!dragOver}
    ondragover={(e) => { e.preventDefault(); dragOver = true; }}
    ondragleave={() => (dragOver = false)}
    ondrop={onDrop}
  >
    <input type="file" multiple accept="audio/*" class="hidden" onchange={onPick} />
    <div class="mx-auto mb-2 grid size-12 place-items-center rounded-full bg-slate-800 text-slate-400">
      <FolderOpen size={22} />
    </div>
    <p class="mt-2 text-sm">
      Arrastra ficheros aquí o <span class="text-cyan-400 underline">elige del disco</span>
    </p>
    <p class="mt-1 text-xs text-slate-500">mp3 · flac · ogg · opus · m4a · aac · wav</p>
  </label>

  {#if items.length > 0}
    <!-- Overrides -->
    <div class="rounded-md border border-slate-800 bg-slate-900 p-3">
      <p class="mb-2 text-xs uppercase tracking-wider text-slate-500">Organizar como…</p>
      <div class="mb-2 grid grid-cols-3 gap-2 text-xs">
        <label
          class="cursor-pointer rounded border px-3 py-1.5 text-center"
          class:border-cyan-500={mode === 'single'}
          class:bg-cyan-500={mode === 'single'}
          class:text-slate-950={mode === 'single'}
          class:border-slate-800={mode !== 'single'}
        >
          <input type="radio" bind:group={mode} value="single" class="sr-only" />
          Canción suelta
        </label>
        <label
          class="cursor-pointer rounded border px-3 py-1.5 text-center"
          class:border-cyan-500={mode === 'new'}
          class:bg-cyan-500={mode === 'new'}
          class:text-slate-950={mode === 'new'}
          class:border-slate-800={mode !== 'new'}
        >
          <input type="radio" bind:group={mode} value="new" class="sr-only" />
          Álbum nuevo / tags del fichero
        </label>
        <label
          class="cursor-pointer rounded border px-3 py-1.5 text-center"
          class:border-cyan-500={mode === 'existing'}
          class:bg-cyan-500={mode === 'existing'}
          class:text-slate-950={mode === 'existing'}
          class:border-slate-800={mode !== 'existing'}
        >
          <input type="radio" bind:group={mode} value="existing" class="sr-only" />
          Añadir a existente
        </label>
      </div>

      {#if mode === 'single'}
        <div class="grid grid-cols-2 gap-2 text-sm">
          <input
            bind:value={artistOv}
            placeholder="Artista (override)"
            class="rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
          />
          <input
            type="number"
            bind:value={yearOv}
            placeholder="Año"
            min="1900"
            max="2100"
            class="rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
          />
        </div>
        <p class="mt-1 text-[10px] text-slate-600">
          Se ignorará el álbum del fichero y quedará como canción suelta. Podrás añadirla a un álbum después.
        </p>
      {:else if mode === 'new'}
        <div class="grid grid-cols-2 gap-2 text-sm">
          <input
            bind:value={artistOv}
            placeholder="Artista (override)"
            class="rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
          />
          <input
            bind:value={albumOv}
            placeholder="Álbum (override)"
            class="rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
          />
          <input
            type="number"
            bind:value={yearOv}
            placeholder="Año"
            min="1900"
            max="2100"
            class="col-span-2 rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
          />
        </div>
        <p class="mt-1 text-[10px] text-slate-600">
          Vacío = se usan los tags ID3/Vorbis del fichero tal cual.
        </p>
      {:else}
        <select
          bind:value={targetAlbumId}
          class="w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs focus:border-cyan-500 focus:outline-none"
        >
          <option value={null}>— seleccionar álbum —</option>
          {#each albums as a}
            <option value={a.id}>{a.title} · {a.artist_name} ({a.track_count})</option>
          {/each}
        </select>
      {/if}
    </div>

    <!-- Listado -->
    <ul class="divide-y divide-slate-900 rounded-md border border-slate-800">
      {#each items as it, i}
        <li class="flex items-center gap-3 px-3 py-2">
          <span class="flex-none">
            {#if it.status === 'pending'}
              <Clock size={14} class="text-slate-500" />
            {:else if it.status === 'uploading'}
              <Loader2 size={14} class="animate-spin text-sky-400" />
            {:else if it.status === 'done'}
              <Check size={14} class="text-cyan-400" />
            {:else}
              <X size={14} class="text-red-400" />
            {/if}
          </span>
          <div class="min-w-0 flex-1">
            {#if it.status === 'pending'}
              <input
                bind:value={it.title}
                placeholder="Título"
                class="w-full rounded border border-slate-800 bg-slate-950 px-2 py-1 text-sm focus:border-cyan-500 focus:outline-none"
              />
            {:else}
              <div class="truncate text-sm">{it.title || it.file.name}</div>
            {/if}
            <div class="mt-0.5 truncate text-xs text-slate-500">{it.file.name} · {formatBytes(it.file.size)}</div>
            {#if it.error}
              <div class="truncate text-xs text-red-400/80" title={it.error}>{it.error}</div>
            {/if}
          </div>
          {#if it.status === 'pending'}
            <button
              onclick={() => removeItem(i)}
              class="grid size-6 place-items-center rounded text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
            ><X size={14} /></button>
          {/if}
        </li>
      {/each}
    </ul>

    <div class="flex flex-wrap gap-2">
      <button
        onclick={uploadAll}
        disabled={uploading || (mode === 'existing' && !targetAlbumId)}
        class="flex-1 rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
      >
        {uploading ? 'Subiendo…' : `Subir ${items.filter((x) => x.status !== 'done').length} ${items.length === 1 ? 'fichero' : 'ficheros'}`}
      </button>
      {#if items.some((x) => x.status === 'done')}
        <button
          onclick={clearDone}
          class="rounded-md border border-slate-800 px-3 py-2 text-xs text-slate-500 hover:bg-slate-800"
        >limpiar completados</button>
      {/if}
    </div>
  {/if}
</div>
