import { useQuery } from '@tanstack/react-query';

import { checkHealth } from '@/api/health';

export function useHealth(refetchInterval?: number) {
  return useQuery({
    queryKey: ['health'],
    queryFn: checkHealth,
    retry: false,
    refetchInterval,
    staleTime: 30 * 1000,
  });
}
