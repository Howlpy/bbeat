<script lang="ts">
  import { FileArchive } from 'lucide-svelte';
  import { auth } from '$lib/auth.svelte';
  import { apiUrl } from '$lib/config';

  let {
    albumId,
    count,
    label = 'Exportar .zip',
    class: klass = 'rounded-lg border border-line px-4 py-2'
  }: { albumId: number; count?: number; label?: string; class?: string } = $props();

  // El <a> no puede mandar el header Authorization, así que el token va en la URL
  // (igual que en el stream y las carátulas).
  const href = $derived(
    auth.appendTokenToUrl(apiUrl(`/api/library/albums/${albumId}/download.zip`))
  );
  const empty = $derived(count === 0);
</script>

{#if !empty}
  <a
    {href}
    download
    class="inline-flex items-center gap-2 text-sm font-medium transition hover:bg-surface-2 {klass}"
    title="Exportar toda la lista en un .zip"
  >
    <FileArchive size={16} /> {label}
  </a>
{/if}
