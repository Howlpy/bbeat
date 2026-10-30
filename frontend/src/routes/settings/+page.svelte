<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
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

<div class="page-narrow">
  <BackButton fallback="/" />
  <h1 class="page-title mb-6">Ajustes</h1>

  <section class="rounded-xl border border-line bg-surface p-5">
    <h2 class="section-title mb-3">Setup base</h2>
    {#if setupComplete === null}
      <p class="text-fg-subtle">Comprobando…</p>
    {:else if setupComplete}
      <p class="inline-flex items-center gap-2 text-accent">
        <CheckCircle2 size={16} /> Configuración base completa.
      </p>
    {:else}
      <p class="inline-flex items-center gap-2 text-warning">
        <AlertTriangle size={16} /> Falta crear directorios de datos.
      </p>
    {/if}
  </section>

  {#if updates.available}
    <section class="mt-6 rounded-xl border border-line bg-surface p-5">
      <h2 class="section-title mb-3">
        <Download size={14} /> Actualizaciones de la app
      </h2>
      <p class="mb-3 text-sm text-fg-muted">
        Comprueba GitHub Releases y actualiza BBeat directamente desde el APK oficial.
      </p>

      {#if updateInfo}
        <div class="mb-3 rounded-lg border border-line bg-bg/60 px-3 py-2 text-sm min-h-11 sm:min-h-10">
          <div class="flex justify-between gap-3">
            <span class="text-fg-subtle">Versión instalada</span>
            <span class="tabular-nums text-fg">{updateInfo.currentVersion}</span>
          </div>
          <div class="mt-1 flex justify-between gap-3">
            <span class="text-fg-subtle">Última versión</span>
            <span class="tabular-nums text-fg">{updateInfo.latestVersion}</span>
          </div>
        </div>
      {/if}

      {#if updateError}
        <p class="mb-3 text-xs text-danger">{updateError}</p>
      {:else if updateInfo && !updateInfo.updateAvailable}
        <p class="mb-3 inline-flex items-center gap-2 text-sm text-accent">
          <CheckCircle2 size={15} /> Ya tienes la última versión.
        </p>
      {:else if updateInfo?.updateAvailable}
        <p class="mb-3 text-sm text-warning">
          BBeat {updateInfo.latestVersion} está disponible.
        </p>
      {/if}

      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          onclick={checkUpdate}
          disabled={updateBusy}
          class="inline-flex items-center gap-2 rounded-lg border border-line-strong px-3 py-2 text-sm text-fg transition hover:bg-surface-2 disabled:opacity-50 min-h-11 sm:min-h-10"
        >
          <RefreshCw size={14} class={updateBusy && !updateInfo?.updateAvailable ? 'animate-spin' : ''} />
          {updateBusy && !updateInfo?.updateAvailable ? 'Comprobando…' : 'Buscar actualizaciones'}
        </button>
        {#if updateInfo?.updateAvailable}
          <button
            type="button"
            onclick={installUpdate}
            disabled={updateBusy}
            class="inline-flex items-center gap-2 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-accent transition  disabled:opacity-50 min-h-11 sm:min-h-10"
          >
            <Download size={14} /> {updateBusy ? 'Descargando…' : 'Descargar e instalar'}
          </button>
        {/if}
      </div>
    </section>
  {/if}


  <p class="mt-6 text-xs text-fg-subtle">
    Más opciones (formato de audio, calidad, plantilla de nombrado, host bind…)
    se podrán editar desde aquí en una fase próxima. Por ahora viven en
    <code class="bg-surface px-1">backend/.env</code>.
  </p>

  <section class="mt-6 rounded-xl border border-line bg-surface p-5">
    <h2 class="section-title mb-3">
      <Smartphone size={14} /> Acceso Subsonic (iPhone y otros clientes)
    </h2>
    <p class="mb-3 text-sm text-fg-muted">
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
            <span class="w-36 shrink-0 text-xs text-fg-subtle">{row.label}</span>
            <input
              type="text"
              readonly
              value={row.value}
              class="min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 py-2.5 tabular-nums text-xs text-fg outline-none min-h-11 sm:min-h-10"
            />
            <button
              type="button"
              onclick={() => copy(row.value, row.key)}
              class="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line px-3 py-2.5 text-xs text-fg-muted transition hover:bg-surface-2 min-h-11 sm:min-h-10"
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
          class="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-fg-muted transition hover:bg-surface-2 disabled:opacity-50 min-h-11 sm:min-h-10"
        >
          <RefreshCw size={14} /> Regenerar
        </button>
        <button
          type="button"
          onclick={revokeToken}
          disabled={subBusy}
          class="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-fg-muted transition hover:bg-surface-2 hover:text-danger disabled:opacity-50 min-h-11 sm:min-h-10"
        >
          <Trash2 size={14} /> Revocar
        </button>
      </div>
    {:else}
      <button
        onclick={genToken}
        disabled={subBusy}
        class="inline-flex items-center gap-2 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-accent transition  disabled:opacity-50 min-h-11 sm:min-h-10"
      >
        <KeyRound size={14} /> {subBusy ? 'Generando…' : 'Generar token de acceso'}
      </button>
    {/if}

    <details class="mt-4 text-xs text-fg-subtle">
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

  <section class="mt-6 rounded-xl border border-line bg-surface p-5">
    <h2 class="section-title mb-3">
      Mantenimiento
    </h2>
    <p class="mb-3 text-sm text-fg-muted">
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
      class="inline-flex items-center gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning transition hover:bg-warning/20 min-h-11 sm:min-h-10"
    >
      <Brush size={14} /> Limpiar caché y recargar
    </button>
  </section>
</div>
