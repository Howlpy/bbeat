// Aviso breve global (se pinta en +layout.svelte).
class ToastState {
  msg = $state<string | null>(null);
  private timer: ReturnType<typeof setTimeout> | undefined;

  show(msg: string, ms = 2200) {
    this.msg = msg;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => (this.msg = null), ms);
  }
}
export const toast = new ToastState();

export const UNAVAILABLE_MSG = 'No disponible sin conexión';
