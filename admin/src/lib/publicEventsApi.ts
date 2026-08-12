import { apiRequest } from './apiClient';

export type PublicEventPrice = {
  currency: string;
  min_price: string;
  is_free: boolean;
};

export type PublicEvent = {
  id: number;
  title: string;
  short_description: string | null;
  category: string | null;
  cover_image_url: string | null;
  start_at: string;
  end_at: string;
  venue_name: string | null;
  venue_city: string | null;
  venue_country: string | null;
  custom_venue_name: string | null;
  custom_address_text: string | null;
  organizer_name: string | null;
  price_summary: PublicEventPrice | null;
};

export type PublicTicketTier = {
  id: number;
  name: string;
  description: string | null;
  price_amount: string;
  currency: string;
  available_quantity: number;
  is_active: boolean;
};

export type PublicEventDetail = PublicEvent & {
  long_description: string | null;
  ticket_tiers: PublicTicketTier[];
};

export async function listUpcomingPublicEvents(): Promise<PublicEvent[]> {
  const response = await apiRequest('/events/discover?date_bucket=upcoming', {
    method: 'GET',
    skipAuth: true,
  });
  return response.json() as Promise<PublicEvent[]>;
}

export async function getPublicEvent(eventId: number): Promise<PublicEventDetail> {
  const response = await apiRequest(`/events/discover/${eventId}`, {
    method: 'GET',
    skipAuth: true,
  });
  return response.json() as Promise<PublicEventDetail>;
}
