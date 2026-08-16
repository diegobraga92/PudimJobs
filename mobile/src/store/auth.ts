import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import * as SecureStore from 'expo-secure-store';

import { User } from '@/types';

export const TOKEN_STORAGE_KEY = 'pudimjobs_token';

interface AuthState {
  token: string | null;
  user: User | null;
  hasHydrated: boolean;
  setSession: (token: string, user?: User) => void;
  setUser: (user: User) => void;
  clear: () => void;
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
      setSession: (token, user) => set({ token, user: user ?? null }),
      setUser: (user) => set({ user }),
      clear: () => set({ token: null, user: null }),
      rehydrated: () => set({ hasHydrated: true }),
    }),
    {
      name: 'pudimjobs_auth',
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
