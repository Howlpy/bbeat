<script lang="ts">
  import { WifiOff } from 'lucide-svelte';
</script>

<!-- Vacío compacto cuando no hay datos en caché y no hay red -->
<div class="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-fg-muted">
  <WifiOff class="mx-auto mb-2 text-fg-subtle" size={22} />
  Sin conexión — aquí aparecerán tus
  <a href="/downloads" class="text-accent underline">descargas</a>
</div>
