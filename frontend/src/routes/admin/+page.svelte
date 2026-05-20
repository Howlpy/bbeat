<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { AlertTriangle, ArrowDown, ArrowUp, Ban, CheckCircle2, Trash2 } from 'lucide-svelte';
  import { api } from '$lib/api';
  import { auth, type AuthUser } from '$lib/auth.svelte';

  let users = $state<AuthUser[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);

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

  onMount(() => {
    if (!auth.user?.is_admin) {
      goto('/');
      return;
    }
    load();
  });
</script>

<div class="mx-auto max-w-3xl px-4 pt-6">
  <h1 class="mb-4 text-2xl font-bold">Admin · Usuarios</h1>

  {#if loading}
    <p class="text-slate-500">Cargando…</p>
  {:else if error}
    <p class="inline-flex items-center gap-2 rounded border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
      <AlertTriangle size={16} /> {error}
    </p>
  {:else}
    <ul class="divide-y divide-slate-900 rounded-md border border-slate-800">
      {#each users as u (u.id)}
        <li class="flex flex-wrap items-center gap-3 p-3">
          <div class="min-w-0 flex-1">
            <div class="flex items-baseline gap-2">
              <span class="font-medium">{u.username}</span>
              {#if u.is_admin}<span class="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">admin</span>{/if}
              {#if !u.is_active}<span class="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] text-red-300">bloqueado</span>{/if}
              {#if u.id === auth.user?.id}<span class="text-[10px] text-slate-500">(tú)</span>{/if}
            </div>
            <div class="text-xs text-slate-500">
              {u.email}
              {#if u.created_at} · alta {new Date(u.created_at).toLocaleDateString('es-ES')}{/if}
            </div>
          </div>
          {#if u.id !== auth.user?.id}
            <div class="flex flex-wrap gap-1">
              {#if u.is_active}
                <button
                  onclick={() => setActive(u, false)}
                  class="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 text-xs transition hover:bg-slate-800"
                ><Ban size={12} /> Bloquear</button>
              {:else}
                <button
                  onclick={() => setActive(u, true)}
                  class="inline-flex items-center gap-1 rounded border border-cyan-700/40 px-2 py-1 text-xs text-cyan-300 transition hover:bg-cyan-950/30"
                ><CheckCircle2 size={12} /> Desbloquear</button>
              {/if}
              <button
                onclick={() => toggleAdmin(u)}
                class="inline-flex items-center gap-1 rounded border border-slate-800 px-2 py-1 text-xs transition hover:bg-slate-800"
              >
                {#if u.is_admin}
                  <ArrowDown size={12} /> Quitar admin
                {:else}
                  <ArrowUp size={12} /> Admin
                {/if}
              </button>
              <button
                onclick={() => del(u)}
                class="grid size-6 place-items-center rounded border border-red-900/50 text-red-300 transition hover:bg-red-950/40"
                title="Borrar usuario"
              ><Trash2 size={12} /></button>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>
