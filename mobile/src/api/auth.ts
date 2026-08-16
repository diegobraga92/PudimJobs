import { LoginResponse, User } from '@/types';
import { apiClient } from './client';

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/api/auth/login', { email, password });
  return data;
}

export async function me(): Promise<User> {
  const { data } = await apiClient.get<User>('/api/auth/me');
  return data;
}
