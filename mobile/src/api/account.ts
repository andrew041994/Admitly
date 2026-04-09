import { apiRequest } from './client';

export type AccountProfile = {
  id: number;
  email: string;
  full_name: string;
  phone_number: string | null;
  is_active: boolean;
  is_verified: boolean;
  my_tickets_count: number;
  my_events_count: number;
  staff_events_count: number;
};

export async function getAccountProfile(): Promise<AccountProfile> {
  return apiRequest<AccountProfile>({ path: '/account/profile', method: 'GET' });
}
