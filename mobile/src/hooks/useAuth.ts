import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { login as apiLogin, me as apiMe } from '@/api/auth';
import { User } from '@/types';
import { useAuthStore } from '@/store/auth';

export function useLogin() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      apiLogin(email, password),
  });
}

export function useMe(enabled = true) {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: apiMe,
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/** Hydrates the auth store when a token exists but the user profile is missing. */
export function useAuthHydration() {
  const queryClient = useQueryClient();
  const { token, user, setUser } = useAuthStore();
  const { data } = useMe(!!token && !user);

  if (data && (!user || user.id !== data.id)) {
    setUser(data as User);
    queryClient.setQueryData(['auth', 'me'], data);
  }

  return { token, user };
}
