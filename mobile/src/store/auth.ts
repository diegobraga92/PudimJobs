import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as SecureStore from 'expo-secure-store';

import { User } from '@/types';

export const TOKEN_STORAGE_KEY = 'pudimjobs_token';

interface AuthState {
  token: string | null;
  user: User | null;
  hasHydrated: boolean;
  /** Set when a 401 invalidates the session (transient — not persisted). */
  sessionExpired: boolean;
  setSession: (token: string, user?: User) => void;
  setUser: (user: User) => void;
  /** Manual sign-out. */
  clear: () => void;
  /** 401 response: drop the session and mark it as expired. */
  expire: () => void;
  rehydrated: () => void;
}

/**
 * Secure session store — mirrors the web AuthService's localStorage token
 * handling, but the JWT (+ user profile) live in the Android/iOS keychain.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      hasHydrated: false,
      sessionExpired: false,
      setSession: (token, user) => set({ token, user: user ?? null }),
      setUser: (user) => set({ user }),
      clear: () => set({ token: null, user: null, sessionExpired: false }),
      expire: () => set({ token: null, user: null, sessionExpired: true }),
      rehydrated: () => set({ hasHydrated: true }),
    }),
    {
      name: 'pudimjobs_auth',
      // sessionExpired is a transient UI flag — never persist it.
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        hasHydrated: state.hasHydrated,
      }),
      storage: createJSONStorage(() => ({
        getItem: (name) => SecureStore.getItemAsync(name),
        setItem: (name, value) => SecureStore.setItemAsync(name, value),
        removeItem: (name) => SecureStore.deleteItemAsync(name),
      })),
      onRehydrateStorage: () => (state) => {
        state?.rehydrated();
      },
    },
  ),
);

export function isAuthenticated(): boolean {
  return !!useAuthStore.getState().token;
}
