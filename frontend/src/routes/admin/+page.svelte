<script lang="ts">
  import BackButton from '$lib/components/ui/BackButton.svelte';
  import Button from '$lib/components/ui/Button.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import AiGenresAdmin from '$lib/components/AiGenresAdmin.svelte';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { AlertTriangle, ArrowDown, ArrowUp, Ban, CheckCircle2, Clock, Check, Trash2, RefreshCw } from 'lucide-svelte';
  import { api } from '$lib/api';
  import { auth, type AuthUser } from '$lib/auth.svelte';

  let users = $state<AuthUser[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

  const pending = $derived(users.filter((u) => !u.is_approved));

  async function approve(u: AuthUser) {
    try {
      await api.updateUser(u.id, { is_approved: true });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function reject(u: AuthUser) {
    if (!confirm(`¿Rechazar y borrar la solicitud de ${u.username}?`)) return;
    try {
      await api.deleteUser(u.id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function load() {
    loading = true;
    try {
      const r = await api.listUsers();
      users = r.items;
      error = null;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function setActive(u: AuthUser, value: boolean) {
    const verb = value ? 'desbloquear' : 'bloquear';
    if (!confirm(`¿${verb[0].toUpperCase()}${verb.slice(1)} a ${u.username}?`)) return;
    try {
      await api.updateUser(u.id, { is_active: value });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleAdmin(u: AuthUser) {
    if (!confirm(`¿Cambiar admin de ${u.username} a ${!u.is_admin ? 'SÍ' : 'NO'}?`)) return;
    try {
      await api.updateUser(u.id, { is_admin: !u.is_admin });
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  async function del(u: AuthUser) {
    if (!confirm(`¿Borrar la cuenta de ${u.username}? Sus álbumes quedarán huérfanos.`)) return;
    try {
      await api.deleteUser(u.id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  // Mantenimiento: re-escanea el disco y espera a que termine.
  let scanning = $state(false);
  let scanMsg = $state<string | null>(null);
  async function rescan() {
    scanning = true;
    scanMsg = null;
    try {
      await api.startScan();
      let st = await api.scanStatus();
      while (st.running) {
        await new Promise((r) => setTimeout(r, 700));
        st = await api.scanStatus();
      }
      scanMsg = 'Escaneo terminado.';
    } catch (e) {
      scanMsg = e instanceof Error ? e.message : String(e);
    } finally {
      scanning = false;
    }
  }

  onMount(() => {
    if (!auth.user?.is_admin) {
      goto('/');
      return;
    }
    load();
  });
</script>

<div class="page-narrow">
  <BackButton fallback="/" />
  <h1 class="page-title mb-6">Admin</h1>

  <section class="mb-8 rounded-xl border border-line bg-surface p-4">
    <h2 class="mb-1 text-sm font-semibold">Mantenimiento</h2>
    <p class="mb-3 text-sm text-fg-muted">Vuelve a leer la carpeta de música y actualiza la biblioteca.</p>
    <Button onclick={rescan} disabled={scanning}>
      <RefreshCw size={16} class={scanning ? 'animate-spin' : ''} />
      {scanning ? 'Escaneando…' : 'Re-escanear disco'}
    </Button>
    {#if scanMsg}<p class="mt-2 text-sm text-fg-muted">{scanMsg}</p>{/if}
  </section>

  <AiGenresAdmin />

  <h2 class="section-title mb-3">Usuarios</h2>

  {#if loading}
    <div class="space-y-2">{#each Array(4) as _}<Skeleton class="h-16 w-full" />{/each}</div>
  {:else if error}
    <p class="inline-flex items-center gap-2 rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
      <AlertTriangle size={16} /> {error}
    </p>
  {:else}
    {#if pending.length}
      <section class="mb-5 rounded-lg border border-warning/40 bg-warning/10 p-4">
        <h2 class="mb-2 flex items-center gap-2 text-sm font-semibold text-warning">
          <Clock size={15} /> Pendientes de aprobación ({pending.length})
        </h2>
        <ul class="space-y-2">
          {#each pending as u (u.id)}
            <li class="flex flex-wrap items-center gap-2">
              <div class="min-w-0 flex-1">
                <span class="font-medium">{u.username}</span>
                <span class="block truncate text-xs text-fg-subtle">{u.email}</span>
              </div>
              <button
                onclick={() => approve(u)}
                class="inline-flex items-center gap-1 rounded-lg bg-accent px-3.5 py-2 text-xs font-semibold text-accent-fg transition hover:bg-accent-hover min-h-11 sm:min-h-10"
              ><Check size={13} /> Aprobar</button>
              <button
                onclick={() => reject(u)}
                class="inline-flex items-center gap-1 rounded-lg border border-danger/40 px-3.5 py-2 text-xs text-danger transition hover:bg-danger/20 min-h-11 sm:min-h-10"
              ><Trash2 size={13} /> Rechazar</button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <ul class="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
      {#each users as u (u.id)}
        <li class="flex flex-wrap items-center gap-3 p-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-baseline gap-2">
              <span class="font-medium">{u.username}</span>
              {#if u.is_admin}<span class="rounded-lg bg-warning/15 px-1.5 py-0.5 text-xs text-warning">admin</span>{/if}
              {#if !u.is_approved}<span class="rounded-lg bg-warning/15 px-1.5 py-0.5 text-xs text-warning">pendiente</span>{/if}
              {#if !u.is_active}<span class="rounded-lg bg-danger/15 px-1.5 py-0.5 text-xs text-danger">bloqueado</span>{/if}
              {#if u.id === auth.user?.id}<span class="text-xs text-fg-subtle">(tú)</span>{/if}
            </div>
            <div class="text-xs text-fg-subtle">
              {u.email}
              {#if u.created_at} · alta {new Date(u.created_at).toLocaleDateString('es-ES')}{/if}
            </div>
          </div>
          {#if u.id !== auth.user?.id}
            <div class="flex flex-wrap gap-1">
              {#if u.is_active}
                <button
                  onclick={() => setActive(u, false)}
                  class="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-2 text-xs transition hover:bg-surface-2 min-h-11 sm:min-h-10"
                ><Ban size={12} /> Bloquear</button>
              {:else}
                <button
                  onclick={() => setActive(u, true)}
                  class="inline-flex items-center gap-1 rounded-lg border border-accent/40 px-3 py-2 text-xs text-accent transition  min-h-11 sm:min-h-10"
                ><CheckCircle2 size={12} /> Desbloquear</button>
              {/if}
              <button
                onclick={() => toggleAdmin(u)}
                class="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-2 text-xs transition hover:bg-surface-2 min-h-11 sm:min-h-10"
              >
                {#if u.is_admin}
                  <ArrowDown size={12} /> Quitar admin
                {:else}
                  <ArrowUp size={12} /> Admin
                {/if}
              </button>
              <button
                onclick={() => del(u)}
                class="grid size-10 place-items-center rounded-lg border border-danger/40 text-danger transition hover:bg-danger/20"
                title="Borrar usuario"
              ><Trash2 size={12} /></button>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
