import { Injectable } from '@angular/core';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'pudimjobs_theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private current: Theme;

  constructor() {
    this.current = this.loadInitial();
    this.apply(this.current);
  }

  get theme(): Theme {
    return this.current;
  }

  get isDark(): boolean {
    return this.current === 'dark';
  }

  toggle(): Theme {
    this.set(this.current === 'dark' ? 'light' : 'dark');
    return this.current;
  }

  set(theme: Theme): void {
    this.current = theme;
    localStorage.setItem(STORAGE_KEY, theme);
    this.apply(theme);
  }

  private apply(theme: Theme): void {
    document.documentElement.dataset['theme'] = theme;
  }

  private loadInitial(): Theme {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
    // Fall back to the operating-system preference.
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return prefersDark ? 'dark' : 'light';
  }
}
