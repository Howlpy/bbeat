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
  let yearOv = $state<number | undefined>(undefined);
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
    try {
      const opts: Parameters<typeof api.uploadTrack>[1] = {};
      if (mode === 'single') {
        opts.as_single = true;
        if (artistOv.trim()) opts.artist = artistOv.trim();
        if (yearOv !== undefined && Number.isFinite(yearOv)) opts.year = yearOv;
      } else if (mode === 'existing' && targetAlbumId) {
        opts.target_album_id = targetAlbumId;
      } else if (mode === 'new') {
        if (albumOv.trim()) opts.album = albumOv.trim();
        if (artistOv.trim()) opts.artist = artistOv.trim();
        if (yearOv !== undefined && Number.isFinite(yearOv)) opts.year = yearOv;
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
    } finally {
      uploading = false;
      onuploaded?.();
    }
  }

  function clearDone() {
    items = items.filter((i) => i.status !== 'done');
  }
</script>

<div class="space-y-3">
  <label
    role="button"
    class="block cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition"
    class:border-accent={dragOver}
    class:bg-accent={dragOver}
    class:bg-opacity-5={dragOver}
    class:border-line={!dragOver}
    ondragover={(e) => { e.preventDefault(); dragOver = true; }}
    ondragleave={() => (dragOver = false)}
    ondrop={onDrop}
  >
    <input type="file" multiple accept="audio/*" class="hidden" onchange={onPick} />
    <div class="mx-auto mb-2 grid size-12 place-items-center rounded-full bg-surface-2 text-fg-muted">
      <FolderOpen size={22} />
    </div>
    <p class="mt-2 text-sm">
      Arrastra ficheros aquí o <span class="text-accent underline">elige del disco</span>
    </p>
    <p class="mt-1 text-xs text-fg-subtle">mp3 · flac · ogg · opus · m4a · aac · wav</p>
  </label>

  {#if items.length > 0}
    <!-- Overrides -->
    <div class="rounded-lg border border-line bg-surface p-3">
      <p class="mb-2 text-xs uppercase tracking-wider text-fg-subtle">Organizar como…</p>
      <div class="mb-2 grid grid-cols-3 gap-2 text-xs">
        <label
          class="cursor-pointer rounded-lg border px-3 py-1.5 text-center"
          class:border-accent={mode === 'single'}
          class:bg-accent={mode === 'single'}
          class:text-accent-fg={mode === 'single'}
          class:border-line={mode !== 'single'}
        >
          <input type="radio" bind:group={mode} value="single" class="sr-only" />
          Canción suelta
        </label>
        <label
          class="cursor-pointer rounded-lg border px-3 py-1.5 text-center"
          class:border-accent={mode === 'new'}
          class:bg-accent={mode === 'new'}
          class:text-accent-fg={mode === 'new'}
          class:border-line={mode !== 'new'}
        >
          <input type="radio" bind:group={mode} value="new" class="sr-only" />
          Álbum nuevo / tags del fichero
        </label>
        <label
          class="cursor-pointer rounded-lg border px-3 py-1.5 text-center"
          class:border-accent={mode === 'existing'}
          class:bg-accent={mode === 'existing'}
          class:text-accent-fg={mode === 'existing'}
          class:border-line={mode !== 'existing'}
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
            class="rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
          />
          <input
            type="number"
            bind:value={yearOv}
            placeholder="Año"
            min="1900"
            max="2100"
            class="rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
          />
        </div>
        <p class="mt-1 text-xs text-fg-subtle">
          Se ignorará el álbum del fichero y quedará como canción suelta. Podrás añadirla a un álbum después.
        </p>
      {:else if mode === 'new'}
        <div class="grid grid-cols-2 gap-2 text-sm">
          <input
            bind:value={artistOv}
            placeholder="Artista (override)"
            class="rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
          />
          <input
            bind:value={albumOv}
            placeholder="Álbum (override)"
            class="rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
          />
          <input
            type="number"
            bind:value={yearOv}
            placeholder="Año"
            min="1900"
            max="2100"
            class="col-span-2 rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
          />
        </div>
        <p class="mt-1 text-xs text-fg-subtle">
          Vacío = se usan los tags ID3/Vorbis del fichero tal cual.
        </p>
      {:else}
        <select
          bind:value={targetAlbumId}
          class="w-full rounded-lg border border-line bg-bg px-2 py-1.5 text-xs focus:border-accent focus:outline-none"
        >
          <option value={null}>— seleccionar álbum —</option>
          {#each albums as a}
            <option value={a.id}>{a.title} · {a.artist_name} ({a.track_count})</option>
          {/each}
        </select>
      {/if}
    </div>

    <!-- Listado -->
    <ul class="divide-y divide-line-strong rounded-lg border border-line">
      {#each items as it, i}
        <li class="flex items-center gap-3 px-3 py-2">
          <span class="flex-none">
            {#if it.status === 'pending'}
              <Clock size={14} class="text-fg-subtle" />
            {:else if it.status === 'uploading'}
              <Loader2 size={14} class="animate-spin text-accent" />
            {:else if it.status === 'done'}
              <Check size={14} class="text-accent" />
            {:else}
              <X size={14} class="text-danger" />
            {/if}
          </span>
          <div class="min-w-0 flex-1">
            {#if it.status === 'pending'}
              <input
                bind:value={it.title}
                placeholder="Título"
                class="w-full rounded-lg border border-line bg-bg px-2 py-1 text-sm focus:border-accent focus:outline-none"
              />
            {:else}
              <div class="truncate text-sm">{it.title || it.file.name}</div>
            {/if}
            <div class="mt-0.5 truncate text-xs text-fg-subtle">{it.file.name} · {formatBytes(it.file.size)}</div>
            {#if it.error}
              <div class="truncate text-xs text-danger/80" title={it.error}>{it.error}</div>
            {/if}
          </div>
          {#if it.status === 'pending'}
            <button
              onclick={() => removeItem(i)}
              class="grid size-10 place-items-center rounded-lg text-fg-subtle transition hover:bg-surface-2 hover:text-danger"
            ><X size={14} /></button>
          {/if}
        </li>
      {/each}
    </ul>

    <div class="flex flex-wrap gap-2">
      <button
        onclick={uploadAll}
        disabled={uploading || (mode === 'existing' && !targetAlbumId)}
        class="flex-1 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-fg hover:bg-accent-hover disabled:opacity-50 min-h-11 sm:min-h-10"
      >
        {uploading ? 'Subiendo…' : `Subir ${items.filter((x) => x.status !== 'done').length} ${items.length === 1 ? 'fichero' : 'ficheros'}`}
      </button>
      {#if items.some((x) => x.status === 'done')}
        <button
          onclick={clearDone}
          class="rounded-lg border border-line px-3 py-2 text-xs text-fg-subtle hover:bg-surface-2 min-h-11 sm:min-h-10"
        >limpiar completados</button>
      {/if}
    </div>
  {/if}
</div>
