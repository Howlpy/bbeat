<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { server } from '$lib/server.svelte';
  import ServerPicker from '$lib/components/ServerPicker.svelte';

  let username = $state('');
  let email = $state('');
  let password = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit() {
    if (busy) return;
    if (server.needsPick) {
      error = 'Elige primero un servidor bbeat.';
      return;
    }
    busy = true;
    error = null;
    try {
      const r = await api.register(username.trim(), email.trim(), password);
      auth.set(r.token, r.user);
      await goto('/');
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex min-h-screen items-center justify-center px-4">
  <div class="w-full max-w-sm">
    <header class="mb-8 text-center">
      <img src="/logo.png" alt="bbeat — tu música, libre" class="mx-auto w-56" />
      <p class="mt-3 text-xs text-slate-500">crear cuenta</p>
    </header>

    <ServerPicker />

    <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="space-y-3">
      <label class="block">
        <span class="text-xs text-slate-400">Nombre de usuario</span>
        <input
          bind:value={username}
          autocomplete="username"
          minlength="2"
          maxlength="40"
          required
          class="mt-1 w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-slate-400">Email</span>
        <input
          type="email"
          bind:value={email}
          autocomplete="email"
          required
          class="mt-1 w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-slate-400">Contraseña <span class="text-slate-600">(mínimo 6)</span></span>
        <input
          type="password"
          bind:value={password}
          autocomplete="new-password"
          minlength="6"
          required
          class="mt-1 w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
        />
      </label>

      {#if error}
        <p class="rounded border border-red-900/50 bg-red-950/30 p-2 text-xs text-red-300">{error}</p>
      {/if}

      <button
        type="submit"
        disabled={busy || !username.trim() || !email.trim() || password.length < 6 || server.needsPick}
        class="w-full rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
      >
        {busy ? 'Creando…' : 'Crear cuenta'}
      </button>
    </form>

    <p class="mt-6 text-center text-xs text-slate-500">
      ¿Ya tienes cuenta?
      <a href="/login" class="text-cyan-400 hover:underline">Entrar</a>
    </p>
  </div>
</div>
