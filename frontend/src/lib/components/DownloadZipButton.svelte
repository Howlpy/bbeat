<script lang="ts">
  import { FileArchive } from 'lucide-svelte';
  import { auth } from '$lib/auth.svelte';
  import { apiUrl } from '$lib/config';

  let {
    albumId,
    count,
    label = 'Descargar .zip',
    class: klass = 'rounded border border-slate-800 px-3 py-1.5'
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
    class="inline-flex items-center gap-1.5 text-sm transition hover:bg-slate-800 {klass}"
    title="Bajar toda la lista en un .zip"
  >
    <FileArchive size={14} /> {label}
  </a>
{/if}
