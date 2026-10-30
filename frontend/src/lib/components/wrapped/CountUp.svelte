<script lang="ts">
  import { onMount } from 'svelte';
  import { fmtNum } from './model';

  // Cuenta de 0 a `value` con easing; sin animación si el usuario la reduce.
  let { value, ms = 1100 }: { value: number; ms?: number } = $props();
  let shown = $state(0);

  onMount(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      shown = value;
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / ms);
      shown = Math.round(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  });
</script>

<span class="tabular-nums">{fmtNum(shown)}</span>
