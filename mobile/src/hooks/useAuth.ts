import { useMutation } from '@tanstack/react-query';

import { login as apiLogin } from '@/api/auth';

export function useLogin() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      apiLogin(email, password),
  });
}
