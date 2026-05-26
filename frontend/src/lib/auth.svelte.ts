import { browser } from '$app/environment';

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  is_active: boolean;
  is_approved: boolean;
  created_at: string | null;
};

const TOKEN_KEY = 'bbeat:token';
const USER_KEY = 'bbeat:user';

class AuthStore {
  token = $state<string | null>(null);
  user = $state<AuthUser | null>(null);
  initialized = $state(false);

  isLoggedIn = $derived(this.token !== null && this.user !== null);

  init() {
    if (!browser || this.initialized) return;
    this.token = localStorage.getItem(TOKEN_KEY);
    const u = localStorage.getItem(USER_KEY);
    if (u) {
      try { this.user = JSON.parse(u); } catch {}
    }
    this.initialized = true;
  }

  set(token: string, user: AuthUser) {
    this.token = token;
    this.user = user;
    if (browser) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  }

  logout() {
    this.token = null;
    this.user = null;
    if (browser) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  }

  authHeader(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  /** Para URLs que no pueden mandar Authorization header (audio/img). */
  appendTokenToUrl(url: string): string {
    if (!this.token) return url;
    const sep = url.includes('?') ? '&' : '?';
    return `${url}${sep}token=${encodeURIComponent(this.token)}`;
  }
}

export const auth = new AuthStore();
