import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useColorScheme } from 'react-native';

import { createTheme, Theme } from './tokens';

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'pudimjobs_theme';

interface ThemeContextValue {
  theme: Theme;
  mode: ThemeMode;
  isDark: boolean;
  /** Mirrors the web ThemeService: toggles and persists the choice. */
  toggle: () => void;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function loadInitial(system: 'light' | 'dark'): ThemeMode {
  // Persisted choice wins; otherwise fall back to the OS preference.
  const stored = globalThis.localStorage?.getItem?.(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') {
    return stored;
  }
  return system === 'dark' ? 'dark' : 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>(() =>
    loadInitial(system === 'dark' ? 'dark' : 'light'),
  );

  // Keep the resolved theme in sync if the persisted value changes externally.
  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEY).then((stored) => {
      if (active && (stored === 'light' || stored === 'dark')) {
        setModeState(stored);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
  }, []);

  const toggle = useCallback(() => {
    setModeState((current) => {
      const next: ThemeMode = current === 'dark' ? 'light' : 'dark';
      AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
      return next;
    });
  }, []);

  const theme = useMemo(() => createTheme(mode === 'dark'), [mode]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, mode, isDark: mode === 'dark', toggle, setMode }),
    [theme, mode, toggle, setMode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within <ThemeProvider>');
  }
  return ctx;
}
