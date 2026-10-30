<script lang="ts">
  import { onDestroy } from 'svelte';
  import { pushBack } from '$lib/backstack.svelte';

  let { users }: { users: { username: string; plays: number }[] } = $props();

  const MAX = 3;
  let open = $state(false);
  let unregister: (() => void) | null = null;

  const shown = $derived(users.slice(0, MAX));
  const extra = $derived(users.length - shown.length);
  // Tooltip web: "ana (5), luis (2)…"
  const title = $derived(users.map((u) => `${u.username} (${u.plays})`).join(', '));

  function close() {
    open = false;
    unregister?.();
    unregister = null;
  }

  function toggle(e: MouseEvent) {
    e.stopPropagation();
    if (open) return close();
    open = true;
    unregister = pushBack(close);
  }

  onDestroy(() => unregister?.());
</script>

{#if users.length > 0}
  <div class="relative flex-none">
    <button
      onclick={toggle}
      class="flex h-10 items-center rounded-full px-1 hover:bg-surface-2"
      {title}
      aria-label="Quién lo escuchó: {title}"
      aria-expanded={open}
    >
      <span class="flex -space-x-1.5">
        {#each shown as u (u.username)}
          <span class="grid size-5 place-items-center rounded-full bg-surface-2 text-[10px] font-semibold uppercase text-fg-muted ring-2 ring-bg">{u.username.charAt(0)}</span>
        {/each}
        {#if extra > 0}
          <span class="grid h-5 min-w-5 place-items-center rounded-full bg-surface-2 px-1 text-[10px] font-semibold text-fg-subtle ring-2 ring-bg">+{extra}</span>
        {/if}
      </span>
    </button>
    {#if open}
      <button class="fixed inset-0 z-40 cursor-default" onclick={close} aria-label="Cerrar"></button>
      <div class="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-line bg-surface py-1 text-xs shadow-xl shadow-black/40">
        <div class="px-3 py-1 text-[11px] uppercase tracking-wider text-fg-subtle">Lo escucharon</div>
        <ul class="max-h-56 overflow-y-auto">
          {#each users as u (u.username)}
            <li class="flex items-center justify-between gap-2 px-3 py-1.5">
              <span class="truncate text-fg">{u.username}</span>
              <span class="flex-none tabular-nums text-fg-muted">{u.plays}</span>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  </div>
{/if}
