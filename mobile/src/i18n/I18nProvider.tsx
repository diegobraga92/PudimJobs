import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLocales } from 'expo-localization';

import { DICTIONARY, TranslationEntry } from './dictionary';

export type Language = 'en' | 'pt-BR';

const STORAGE_KEY = 'pudimjobs_language';

interface I18nContextValue {
  lang: Language;
  current: Language;
  /** Returns the translation for `key`, interpolating `{placeholder}` tokens. */
  t: (key: string, params?: Record<string, string | number | null | undefined>) => string;
  /** Switches between English and Brazilian Portuguese. */
  toggle: () => Language;
  setLanguage: (lang: Language) => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function loadInitial(): Language {
  const stored = globalThis.localStorage?.getItem?.(STORAGE_KEY);
  if (stored === 'en' || stored === 'pt-BR') {
    return stored;
  }
  const device = getLocales()[0]?.languageCode?.toLowerCase();
  return device === 'pt' ? 'pt-BR' : 'en';
}

function translate(
  lang: Language,
  key: string,
  params?: Record<string, string | number | null | undefined>,
): string {
  const entry: TranslationEntry | undefined = DICTIONARY[key];
  let value = entry ? entry[lang] : key;
  if (params) {
    value = value.replace(/\{(\w+)\}/g, (match, name: string) =>
      params[name] !== undefined ? String(params[name]) : match,
    );
  }
  return value;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(() => loadInitial());

  useEffect(() => {
    let active = true;
    AsyncStorage.getItem(STORAGE_KEY).then((stored) => {
      if (active && (stored === 'en' || stored === 'pt-BR')) {
        setLangState(stored);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLangState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
  }, []);

  const toggle = useCallback((): Language => {
    const next: Language = lang === 'en' ? 'pt-BR' : 'en';
    setLangState(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => undefined);
    return next;
  }, [lang]);

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      current: lang,
      t: (key, params) => translate(lang, key, params),
      toggle,
      setLanguage,
    }),
    [lang, toggle, setLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used within <I18nProvider>');
  }
  return ctx;
}
