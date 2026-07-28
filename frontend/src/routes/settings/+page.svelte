<script lang="ts">
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';
  import { AlertTriangle, Brush, CheckCircle2, Copy, Download, KeyRound, RefreshCw, Smartphone, Trash2 } from 'lucide-svelte';
  import { api } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { server } from '$lib/server.svelte';
  import { updates, type UpdateInfo } from '$lib/updates';

  let setupComplete = $state<boolean | null>(null);
  let message = $state<{ kind: 'ok' | 'err'; text: string } | null>(null);
  let updateInfo = $state<UpdateInfo | null>(null);
  let updateBusy = $state(false);
  let updateError = $state<string | null>(null);

  async function checkUpdate() {
    updateBusy = true;
    updateError = null;
    try {
      updateInfo = await updates.check();
    } catch (error) {
      updateError = error instanceof Error ? error.message : String(error);
    } finally {
      updateBusy = false;
    }
  }

  async function installUpdate() {
    if (!updateInfo?.downloadUrl) return;
    updateBusy = true;
    updateError = null;
    try {
      await updates.install(updateInfo.downloadUrl);
    } catch (error) {
      updateError = error instanceof Error ? error.message : String(error);
    } finally {
      updateBusy = false;
    }
  }

  // ── Acceso Subsonic ──
  let subToken = $state<string | null>(auth.user?.subsonic_token ?? null);
  let subBusy = $state(false);
  let subCopied = $state<'url' | 'user' | 'token' | null>(null);
  const subServerUrl = $derived(
    server.base || (browser ? window.location.origin : 'https://tu-servidor')
  );

  function persistUser(token: string | null) {
    subToken = token;
    if (auth.token && auth.user) {
      auth.set(auth.token, { ...auth.user, subsonic_token: token });
    }
  }

  async function genToken() {
    subBusy = true;
    try {
      const r = await api.generateSubsonicToken();
      persistUser(r.subsonic_token);
    } catch (e) {
      message = { kind: 'err', text: e instanceof Error ? e.message : String(e) };
    } finally {
      subBusy = false;
    }
  }

  async function revokeToken() {
    if (!confirm('¿Revocar el token? Los clientes Subsonic dejarán de conectarse.')) return;
    subBusy = true;
    try {
      await api.revokeSubsonicToken();
      persistUser(null);
    } finally {
      subBusy = false;
    }
  }

  async function copy(text: string, which: 'url' | 'user' | 'token') {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for iOS Safari where clipboard API may fail
      const el = document.createElement('input');
      el.value = text;
      el.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(el);
      el.focus();
      el.select();
      el.setSelectionRange(0, text.length);
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    subCopied = which;
    setTimeout(() => (subCopied = null), 1500);
  }

  async function loadAll() {
    const h = await api.health();
    setupComplete = h.setup_complete;
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
      <p class="inline-flex items-center gap-2 text-cyan-400">
        <CheckCircle2 size={16} /> Configuración base completa.
      </p>
    {:else}
      <p class="inline-flex items-center gap-2 text-amber-400">
        <AlertTriangle size={16} /> Falta crear directorios de datos.
      </p>
    {/if}
  </section>

  {#if updates.available}
    <section class="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-4">
      <h2 class="mb-2 inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-500">
        <Download size={14} /> Actualizaciones de la app
      </h2>
      <p class="mb-3 text-xs text-slate-400">
        Comprueba GitHub Releases y actualiza BBeat directamente desde el APK oficial.
      </p>

      {#if updateInfo}
        <div class="mb-3 rounded border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm">
          <div class="flex justify-between gap-3">
            <span class="text-slate-500">Versión instalada</span>
            <span class="font-mono text-slate-200">{updateInfo.currentVersion}</span>
          </div>
          <div class="mt-1 flex justify-between gap-3">
            <span class="text-slate-500">Última versión</span>
            <span class="font-mono text-slate-200">{updateInfo.latestVersion}</span>
          </div>
        </div>
      {/if}

      {#if updateError}
        <p class="mb-3 text-xs text-red-400">{updateError}</p>
      {:else if updateInfo && !updateInfo.updateAvailable}
        <p class="mb-3 inline-flex items-center gap-2 text-sm text-cyan-400">
          <CheckCircle2 size={15} /> Ya tienes la última versión.
        </p>
      {:else if updateInfo?.updateAvailable}
        <p class="mb-3 text-sm text-amber-300">
          BBeat {updateInfo.latestVersion} está disponible.
        </p>
      {/if}

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          onclick={checkUpdate}
          disabled={updateBusy}
          class="inline-flex items-center gap-2 rounded border border-slate-700 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw size={14} class={updateBusy && !updateInfo?.updateAvailable ? 'animate-spin' : ''} />
          {updateBusy && !updateInfo?.updateAvailable ? 'Comprobando…' : 'Buscar actualizaciones'}
        </button>
        {#if updateInfo?.updateAvailable}
          <button
            type="button"
            onclick={installUpdate}
            disabled={updateBusy}
            class="inline-flex items-center gap-2 rounded border border-cyan-700/50 bg-cyan-950/30 px-3 py-2 text-sm text-cyan-200 transition hover:bg-cyan-950/50 disabled:opacity-50"
          >
            <Download size={14} /> {updateBusy ? 'Descargando…' : 'Descargar e instalar'}
          </button>
        {/if}
      </div>
    </section>
  {/if}


  <p class="mt-6 text-xs text-slate-600">
    Más opciones (formato de audio, calidad, plantilla de nombrado, host bind…)
    se podrán editar desde aquí en una fase próxima. Por ahora viven en
    <code class="bg-slate-900 px-1">backend/.env</code>.
  </p>

  <section class="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-4">
    <h2 class="mb-2 inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-500">
      <Smartphone size={14} /> Acceso Subsonic (iPhone y otros clientes)
    </h2>
    <p class="mb-3 text-xs text-slate-400">
      Bbeat habla el protocolo <strong>Subsonic</strong>, así que puedes escuchar tu
      música desde apps de terceros —ideal si tienes iPhone. Genera un token y úsalo
      como contraseña en el cliente (tu contraseña normal no sirve ahí).
    </p>

    {#if subToken}
      <div class="space-y-2">
        {#each [
          { label: 'Servidor', value: subServerUrl, key: 'url' as const },
          { label: 'Usuario', value: auth.user?.username ?? '', key: 'user' as const },
          { label: 'Contraseña (token)', value: subToken, key: 'token' as const }
        ] as row}
          <div class="flex items-center gap-2">
            <span class="w-36 shrink-0 text-xs text-slate-500">{row.label}</span>
            <input
              type="text"
              readonly
              value={row.value}
              class="min-w-0 flex-1 rounded border border-slate-800 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-200 outline-none"
            />
            <button
              type="button"
              onclick={() => copy(row.value, row.key)}
              class="inline-flex shrink-0 items-center gap-1 rounded border border-slate-800 px-2 py-1.5 text-xs text-slate-400 transition hover:bg-slate-800"
              title="Copiar"
            >
              <Copy size={13} /> {subCopied === row.key ? '¡Copiado!' : 'Copiar'}
            </button>
          </div>
        {/each}
      </div>

      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onclick={genToken}
          disabled={subBusy}
          class="inline-flex items-center gap-2 rounded border border-slate-800 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-800 disabled:opacity-50"
        >
          <RefreshCw size={14} /> Regenerar
        </button>
        <button
          type="button"
          onclick={revokeToken}
          disabled={subBusy}
          class="inline-flex items-center gap-2 rounded border border-slate-800 px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-red-400 disabled:opacity-50"
        >
          <Trash2 size={14} /> Revocar
        </button>
      </div>
    {:else}
      <button
        onclick={genToken}
        disabled={subBusy}
        class="inline-flex items-center gap-2 rounded border border-cyan-700/50 bg-cyan-950/30 px-3 py-2 text-sm text-cyan-200 transition hover:bg-cyan-950/50 disabled:opacity-50"
      >
        <KeyRound size={14} /> {subBusy ? 'Generando…' : 'Generar token de acceso'}
      </button>
    {/if}

    <details class="mt-4 text-xs text-slate-500">
      <summary class="cursor-pointer">¿Qué app uso?</summary>
      <ul class="mt-2 list-disc space-y-1 pl-5">
        <li><strong>iPhone/iPad:</strong> Amperfy (gratis), play:Sub o substreamer.</li>
        <li><strong>Android:</strong> Symfonium, Tempo o DSub (aunque tienes la app nativa de Bbeat).</li>
        <li>Multiplataforma de escritorio: Sonixd, Feishin.</li>
      </ul>
      <p class="mt-2">
        En el cliente, añade un servidor con la URL, tu usuario y el token como
        contraseña. Si te pide "versión mínima", cualquiera vale.
      </p>
    </details>
  </section>

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
      class="inline-flex items-center gap-2 rounded border border-amber-700/40 bg-amber-950/30 px-3 py-2 text-sm text-amber-200 transition hover:bg-amber-950/50"
    >
      <Brush size={14} /> Limpiar caché y recargar
    </button>
  </section>
</div>
