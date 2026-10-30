<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { server } from '$lib/server.svelte';
  import ServerPicker from '$lib/components/ServerPicker.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  let login = $state('');
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
      <img src="/logo.png" alt="bbeat — tu música, libre" class="mx-auto w-56" />
      <p class="mt-3 text-sm text-fg-muted">inicia sesión para entrar</p>
    </header>

    <ServerPicker />

    <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="space-y-3">
      <label class="block">
        <span class="text-sm text-fg-muted">Usuario o email</span>
        <input
          bind:value={login}
          autocomplete="username"
          required
          class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-sm text-fg-muted">Contraseña</span>
        <input
          type="password"
          bind:value={password}
          autocomplete="current-password"
          required
          class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
        />
      </label>

      {#if error}
        <p class="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>
      {/if}

      <Button type="submit" variant="primary" size="lg" class="w-full"
        disabled={busy || !login.trim() || !password || server.needsPick}
        >
        {busy ? 'Entrando…' : 'Entrar'}
      </Button>
    </form>

    <p class="mt-6 text-center text-sm text-fg-muted">
      ¿Sin cuenta?
      <a href="/register" class="text-accent hover:underline">Crear una</a>
    </p>
  </div>
</div>
