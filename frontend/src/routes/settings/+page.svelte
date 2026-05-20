<script lang="ts">
  import { onMount } from 'svelte';
  import { api, formatBytes, type SpotifyAuthStatus } from '$lib/api';

  let setupComplete = $state<boolean | null>(null);
  let cookies = $state<SpotifyAuthStatus | null>(null);
  let uploading = $state(false);
  let message = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);
  let fileInput = $state<HTMLInputElement | null>(null);

  async function loadAll() {
    const [h, c] = await Promise.all([
      fetch('/api/setup/status').then((r) => r.json()),
      api.spotifyAuthStatus()
    ]);
    setupComplete = h.setup_complete;
    cookies = c;
  }

  async function onUpload(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    uploading = true;
    message = null;
    try {
      const r = await api.uploadCookies(file);
      message = { kind: 'ok', text: `Cookies subidas (${formatBytes(r.size)}).` };
      await loadAll();
    } catch (e) {
      message = { kind: 'err', text: e instanceof Error ? e.message : String(e) };
    } finally {
      uploading = false;
      if (fileInput) fileInput.value = '';
    }
  }

  async function onDelete() {
    if (!confirm('¿Borrar el fichero de cookies de Spotify?')) return;
    await api.deleteCookies();
    message = { kind: 'ok', text: 'Cookies eliminadas.' };
    await loadAll();
  }

  onMount(loadAll);
</script>

<div class="mx-auto max-w-2xl px-4 pt-6">
  <h1 class="mb-4 text-2xl font-bold">Ajustes</h1>

  <section class="rounded-lg border border-slate-800 bg-slate-900 p-4">
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">Setup base</h2>
    {#if setupComplete === null}
      <p class="text-slate-500">Comprobando…</p>
    {:else if setupComplete}
      <p class="text-cyan-400">✓ Credenciales de Spotify Developer configuradas.</p>
    {:else}
      <p class="text-amber-400">⚠ Faltan SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET en backend/.env</p>
    {/if}
  </section>

  <section class="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-4">
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">
      Cookies de Spotify (para Votify)
    </h2>
    <p class="mb-3 text-xs text-slate-400">
      Necesarias para descargar el audio directo de Spotify (alta calidad).
      Sin ellas, Bbeat usará yt-dlp como fallback automático.
    </p>

    {#if cookies}
      {#if cookies.cookies_configured}
        <div class="mb-3 rounded border border-cyan-900/50 bg-cyan-950/30 p-3 text-sm">
          <div class="text-cyan-400">✓ Cookies configuradas</div>
          <div class="mt-1 text-xs text-slate-500">
            {cookies.size ? formatBytes(cookies.size) : '—'}
            {#if cookies.mtime} · subidas {new Date(cookies.mtime * 1000).toLocaleString('es-ES')}{/if}
          </div>
        </div>
      {:else}
        <div class="mb-3 rounded border border-slate-800 bg-slate-950 p-3 text-sm text-slate-400">
          Sin cookies. Bbeat usará yt-dlp.
        </div>
      {/if}
    {/if}

    <div class="flex flex-wrap items-center gap-2">
      <label class="cursor-pointer rounded-md border border-slate-800 px-3 py-2 text-sm hover:bg-slate-800">
        <input
          bind:this={fileInput}
          type="file"
          accept=".txt,text/plain"
          class="hidden"
          onchange={onUpload}
          disabled={uploading}
        />
        {uploading ? 'Subiendo…' : 'Subir cookies.txt'}
      </label>
      {#if cookies?.cookies_configured}
        <button
          onclick={onDelete}
          class="rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-red-400"
        >
          Borrar
        </button>
      {/if}
    </div>

    {#if message}
      <p
        class="mt-3 text-xs"
        class:text-cyan-400={message.kind === 'ok'}
        class:text-red-400={message.kind === 'err'}
      >{message.text}</p>
    {/if}

    <details class="mt-4 text-xs text-slate-500">
      <summary class="cursor-pointer">¿Cómo exporto las cookies?</summary>
      <ol class="mt-2 list-decimal space-y-1 pl-5">
        <li>Inicia sesión en <code>open.spotify.com</code> con tu cuenta dedicada de Bbeat.</li>
        <li>Instala una extensión tipo "Get cookies.txt LOCALLY" en Chrome o Firefox.</li>
        <li>Mientras estás en la pestaña de Spotify, exporta cookies en formato Netscape.</li>
        <li>Súbelo aquí.</li>
      </ol>
    </details>
  </section>

  <p class="mt-6 text-xs text-slate-600">
    Más opciones (formato de audio, calidad, plantilla de nombrado, host bind…)
    se podrán editar desde aquí en una fase próxima. Por ahora viven en
    <code class="bg-slate-900 px-1">backend/.env</code>.
  </p>

  <section class="mt-8 rounded-lg border border-slate-800 bg-slate-900 p-4">
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-500">
      Mantenimiento
    </h2>
    <p class="mb-3 text-xs text-slate-400">
      Si Bbeat empieza a fallar de manera rara (cache zombi del service worker,
      versión vieja del frontend…), borra el caché y refresca:
    </p>
    <button
      onclick={async () => {
        try {
          if ('serviceWorker' in navigator) {
            const regs = await navigator.serviceWorker.getRegistrations();
            for (const r of regs) await r.unregister();
          }
          if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map((k) => caches.delete(k)));
          }
        } finally {
          location.reload();
        }
      }}
      class="rounded-md border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-200 hover:bg-amber-950/50"
    >
      🧹 Limpiar caché y recargar
    </button>
  </section>
</div>
