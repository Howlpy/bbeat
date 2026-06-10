import { api, type Job, type JobStats } from './api';

class JobsStore {
  items = $state<Job[]>([]);
  stats = $state<JobStats>({ pending: 0, running: 0, done: 0, failed: 0, total: 0 });
  lastError = $state<string | null>(null);
  loading = $state(false);

  active = $derived(this.stats.pending + this.stats.running);
  hasFailed = $derived(this.stats.failed > 0);

  private timer: ReturnType<typeof setTimeout> | null = null;
  private onVisible: (() => void) | null = null;

  async refresh() {
    this.loading = true;
    try {
      const r = await api.listJobs(200);
      this.items = r.items;
      this.stats = r.stats;
      this.lastError = null;
    } catch (e) {
      this.lastError = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
    }
  }

  start() {
    if (this.timer) return;
    const loop = async () => {
      // Con la pestaña en segundo plano no hay nada que mirar: no machacamos
      // la API del servidor casero. Al volver al foco, refrescamos al instante.
      if (typeof document !== 'undefined' && document.hidden) {
        this.timer = setTimeout(loop, 10000);
        return;
      }
      await this.refresh();
      // 700ms cuando hay jobs corriendo (para ver el progreso fluido),
      // 1.5s con jobs en cola, 15s en idle para ahorrar tráfico/CPU.
      const ms = this.stats.running > 0 ? 700 : this.active > 0 ? 1500 : 15000;
      this.timer = setTimeout(loop, ms);
    };
    if (typeof document !== 'undefined') {
      this.onVisible = () => {
        if (!document.hidden && this.timer) {
          clearTimeout(this.timer);
          this.timer = null;
          this.start();
        }
      };
      document.addEventListener('visibilitychange', this.onVisible);
    }
    loop();
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (this.onVisible && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.onVisible);
      this.onVisible = null;
    }
  }
}

export const jobs = new JobsStore();
