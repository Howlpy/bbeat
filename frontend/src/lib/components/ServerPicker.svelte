<script lang="ts">
  import { Server, Star, Trash2, Plus, Check, Loader2 } from 'lucide-svelte';
  import { server, normalizeServer } from '$lib/server.svelte';

  let input = $state('');
  let checking = $state(false);
  let msg = $state<{ ok: boolean; text: string } | null>(null);

  // Comprueba que la URL responde como un servidor bbeat (/api/health).
  async function ping(url: string): Promise<boolean> {
    try {
      const res = await fetch(normalizeServer(url) + '/api/health');
      if (!res.ok) return false;
      const j = await res.json();
      return typeof j?.status === 'string';
    } catch {
      return false;
    }
  }

  async function add() {
    const u = normalizeServer(input);
    if (!u || checking) return;
    checking = true;
    msg = null;
    const ok = await ping(u);
    checking = false;
    if (ok) {
      server.addFavorite(u);
      input = '';
      msg = { ok: true, text: 'Conectado ✓' };
    } else {
      msg = { ok: false, text: 'No responde como un servidor bbeat' };
    }
  }
</script>

{#if server.pickable}
  <div class="mb-6 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
    <div class="mb-3 flex items-center gap-2 text-slate-400">
      <Server size={15} />
      <span class="text-xs font-semibold uppercase tracking-wider">Servidor</span>
    </div>

    {#if server.favorites.length}
      <ul class="mb-3 space-y-1.5">
        {#each server.favorites as fav (fav)}
          <li class="flex items-center gap-2">
            <button
              onclick={() => { server.select(fav); msg = null; }}
              class="flex flex-1 items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition {server.current === fav ? 'border-cyan-500 bg-cyan-500/10' : 'border-slate-800 hover:bg-slate-800/50'}"
            >
              {#if server.current === fav}
                <Check size={14} class="flex-none text-cyan-400" />
              {:else}
                <Star size={14} class="flex-none text-slate-600" />
              {/if}
              <span class="truncate">{fav.replace(/^https?:\/\//, '')}</span>
            </button>
            <button
              onclick={() => server.removeFavorite(fav)}
              class="grid size-8 flex-none place-items-center rounded text-slate-600 hover:bg-slate-800 hover:text-red-400"
              aria-label="Quitar servidor"
            ><Trash2 size={14} /></button>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="flex items-center gap-2">
      <input
        bind:value={input}
        placeholder="bbeat.tuservidor.com"
        autocapitalize="off"
        autocorrect="off"
        spellcheck="false"
        onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
        class="min-w-0 flex-1 rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm focus:border-cyan-500 focus:outline-none"
      />
      <button
        onclick={add}
        disabled={checking || !input.trim()}
        class="grid size-9 flex-none place-items-center rounded-md bg-slate-800 text-cyan-400 hover:bg-slate-700 disabled:opacity-50"
        aria-label="Añadir servidor"
      >
        {#if checking}<Loader2 size={16} class="animate-spin" />{:else}<Plus size={16} />{/if}
      </button>
    </div>

    {#if msg}
      <p class="mt-2 text-xs {msg.ok ? 'text-cyan-400' : 'text-red-400'}">{msg.text}</p>
    {:else if server.needsPick}
      <p class="mt-2 text-xs text-amber-400/80">Añade tu servidor bbeat para entrar.</p>
    {/if}
  </div>
{/if}
