<script lang="ts">
  import Logo from '$lib/components/ui/Logo.svelte';
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { auth } from '$lib/auth.svelte';
  import { server } from '$lib/server.svelte';
  import ServerPicker from '$lib/components/ServerPicker.svelte';
  import Button from '$lib/components/ui/Button.svelte';

  let username = $state('');
  let email = $state('');
  let password = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);
  let pending = $state(false);

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
      if (!r.token) {
        // Cuenta creada pero pendiente de que un admin la apruebe.
        pending = true;
        return;
      }
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
      <Logo />
      <p class="mt-3 text-sm text-fg-muted">crear cuenta</p>
    </header>

    {#if pending}
      <div class="rounded-xl border border-accent/40 bg-accent-soft p-5 text-center">
        <p class="text-sm font-medium text-accent">Cuenta creada ✓</p>
        <p class="mt-2 text-xs text-fg-muted">
          Está <b>pendiente de aprobación</b> por el administrador. Cuando te aprueben
          podrás iniciar sesión.
        </p>
        <a href="/login" class="mt-4 inline-block text-xs text-accent hover:underline">Volver a entrar</a>
      </div>
    {:else}
    <ServerPicker />

    <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="space-y-3">
      <label class="block">
        <span class="text-sm text-fg-muted">Nombre de usuario</span>
        <input
          bind:value={username}
          autocomplete="username"
          minlength="2"
          maxlength="40"
          required
          class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-sm text-fg-muted">Email</span>
        <input
          type="email"
          bind:value={email}
          autocomplete="email"
          required
          class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
        />
      </label>
      <label class="block">
        <span class="text-sm text-fg-muted">Contraseña <span class="text-fg-subtle">(mínimo 6)</span></span>
        <input
          type="password"
          bind:value={password}
          autocomplete="new-password"
          minlength="6"
          required
          class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:border-accent focus:outline-none"
        />
      </label>

      {#if error}
        <p class="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>
      {/if}

      <Button type="submit" variant="primary" size="lg" class="w-full"
        disabled={busy || !username.trim() || !email.trim() || password.length < 6 || server.needsPick}
        >
        {busy ? 'Creando…' : 'Crear cuenta'}
      </Button>
    </form>

    <p class="mt-6 text-center text-sm text-fg-muted">
      ¿Ya tienes cuenta?
      <a href="/login" class="text-accent hover:underline">Entrar</a>
    </p>
    {/if}
  </div>
</div>
