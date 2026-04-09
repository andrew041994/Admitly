import { apiRequest } from './client';

export type TicketTierCreatePayload = {
  name: string;
  description?: string | null;
  price_amount: string;
  currency: string;
  quantity_total: number;
  min_per_order: number;
  max_per_order: number;
  is_active?: boolean;
  sort_order?: number;
};

export type CreateEventPayload = {
  title: string;
  short_description?: string | null;
  long_description?: string | null;
  category?: string | null;
  cover_image_url?: string | null;
  start_at: string;
  end_at: string;
  doors_open_at?: string | null;
  sales_start_at?: string | null;
  sales_end_at?: string | null;
  timezone?: string;
  custom_venue_name?: string | null;
  custom_address_text?: string | null;
  refund_policy_text?: string | null;
  terms_text?: string | null;
  ticket_tiers: TicketTierCreatePayload[];
};

export type CreateEventResponse = {
  id: number;
  organizer_id: number;
  title: string;
  slug: string;
  status: string;
  timezone: string;
  custom_venue_name: string | null;
  custom_address_text: string | null;
  ticket_tiers: Array<{ id: number; name: string }>;
};

export type MyEventItem = {
  id: number;
  title: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  visibility: string;
  venue_name: string | null;
  venue_city: string | null;
  custom_venue_name: string | null;
  is_active: boolean;
  is_upcoming: boolean;
  is_ended: boolean;
};

export type EventDashboard = {
  event_id: number;
  tickets_sold: number;
  gross_revenue: number;
  attendees_admitted: number;
  attendees_remaining: number;
  total_ticket_capacity: number;
  transfer_count: number;
  voided_ticket_count: number;
  refunded_ticket_count: number;
  live_checkin_percentage: number;
  active_staff_assigned: number;
  tier_metrics: Array<{
    ticket_tier_id: number;
    name: string;
    sold_count: number;
    remaining_count: number;
    gross_revenue: number;
    currency: string;
  }>;
  recent_checkins: Array<{
    ticket_id: number;
    checked_in_at: string;
    checked_in_by_user_id: number | null;
  }>;
};

export type EventStaffAssignment = {
  id: number;
  event_id: number;
  user_id: number;
  role: string;
  created_at: string;
  invited_by_user_id: number | null;
  is_active: boolean;
  is_effective_active: boolean;
};

export type UserSearchResult = {
  id: number;
  full_name: string;
  email: string;
  phone: string | null;
};

export async function createEvent(payload: CreateEventPayload): Promise<CreateEventResponse> {
  return apiRequest<CreateEventResponse>({ path: '/events', method: 'POST', body: JSON.stringify(payload) });
}

export async function listMyEvents(activeOnly = false): Promise<MyEventItem[]> {
  const query = activeOnly ? '?active_only=true' : '';
  return apiRequest<MyEventItem[]>({ path: `/events/mine${query}`, method: 'GET' });
}

export async function listMyActiveEvents(): Promise<MyEventItem[]> {
  return apiRequest<MyEventItem[]>({ path: '/events/mine/active', method: 'GET' });
}

export async function getEventDashboard(eventId: number): Promise<EventDashboard> {
  return apiRequest<EventDashboard>({ path: `/events/${eventId}/dashboard`, method: 'GET' });
}

export async function listEventStaff(eventId: number): Promise<EventStaffAssignment[]> {
  return apiRequest<EventStaffAssignment[]>({ path: `/events/${eventId}/staff`, method: 'GET' });
}

export async function assignCheckinStaff(eventId: number, userId: number): Promise<EventStaffAssignment> {
  return apiRequest<EventStaffAssignment>({
    path: `/events/${eventId}/staff`,
    method: 'POST',
    body: JSON.stringify({ user_id: userId, role: 'checkin' }),
  });
}

export async function removeEventStaff(eventId: number, staffId: number): Promise<void> {
  await apiRequest<unknown>({ path: `/events/${eventId}/staff/${staffId}`, method: 'DELETE' });
}

export async function searchUsers(q: string): Promise<UserSearchResult[]> {
  const params = new URLSearchParams({ q });
  return apiRequest<UserSearchResult[]>({ path: `/users/search?${params.toString()}`, method: 'GET' });
}
