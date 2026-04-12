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

export type StaffEvent = {
  event_id: number;
  title: string;
  start_at: string;
  end_at: string | null;
  timezone: string | null;
  venue_name: string | null;
  role: string | null;
  status: string | null;
};

export async function getAccountProfile(): Promise<AccountProfile> {
  return apiRequest<AccountProfile>({ path: '/account/profile', method: 'GET' });
}

export async function listMyStaffEvents(): Promise<StaffEvent[]> {
  return apiRequest<StaffEvent[]>({ path: '/account/staff-events', method: 'GET' });
}
