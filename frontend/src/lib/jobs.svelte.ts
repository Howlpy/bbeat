import { api, type Job, type JobStats } from './api';

class JobsStore {
  items = $state<Job[]>([]);
  stats = $state<JobStats>({ pending: 0, running: 0, done: 0, failed: 0, total: 0 });
  lastError = $state<string | null>(null);
  loading = $state(false);

  active = $derived(this.stats.pending + this.stats.running);
  hasFailed = $derived(this.stats.failed > 0);

  private timer: ReturnType<typeof setTimeout> | null = null;

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
      await this.refresh();
      // 700ms cuando hay jobs corriendo (para ver el progreso fluido),
      // 6s en idle para ahorrar tráfico.
      const ms = this.stats.running > 0 ? 700 : this.active > 0 ? 1500 : 6000;
      this.timer = setTimeout(loop, ms);
    };
    loop();
  }

  stop() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}

export const jobs = new JobsStore();
