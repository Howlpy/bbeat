<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { auth } from '$lib/auth.svelte';

  let login = $state('');
  let password = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  async function submit() {
    if (busy) return;
    busy = true;
    error = null;
    try {
      const r = await api.login(login.trim(), password);
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
      <h1 class="text-3xl font-bold">
        <span class="text-emerald-400">B</span>beat
      </h1>
      <p class="mt-1 text-xs text-neutral-500">inicia sesión para entrar</p>
    </header>

    <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="space-y-3">
      <label class="block">
        <span class="text-xs text-neutral-400">Usuario o email</span>
        <input
          bind:value={login}
          autocomplete="username"
          required
          class="mt-1 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-xs text-neutral-400">Contraseña</span>
        <input
          type="password"
          bind:value={password}
          autocomplete="current-password"
          required
          class="mt-1 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
        />
      </label>

      {#if error}
        <p class="rounded border border-red-900/50 bg-red-950/30 p-2 text-xs text-red-300">{error}</p>
      {/if}

      <button
        type="submit"
        disabled={busy || !login.trim() || !password}
        class="w-full rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-neutral-950 hover:bg-emerald-400 disabled:opacity-50"
      >
        {busy ? 'Entrando…' : 'Entrar'}
      </button>
    </form>

    <p class="mt-6 text-center text-xs text-neutral-500">
      ¿Sin cuenta?
      <a href="/register" class="text-emerald-400 hover:underline">Crear una</a>
    </p>
  </div>
</div>
