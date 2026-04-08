import { apiRequest } from './client';

export type EventPriceSummary = {
  currency: string;
  min_price: string;
  is_free: boolean;
};

export type EventDiscoveryItem = {
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
  price_summary: EventPriceSummary | null;
};

export type EventDiscoveryTicketTier = {
  id: number;
  name: string;
  description: string | null;
  price_amount: string;
  currency: string;
  min_per_order: number;
  max_per_order: number;
  available_quantity: number;
  is_active: boolean;
};

export type EventDiscoveryDetail = EventDiscoveryItem & {
  long_description: string | null;
  ticket_tiers: EventDiscoveryTicketTier[];
};

export type DiscoveryFilters = {
  query?: string;
  category?: string;
  dateBucket?: 'today' | 'this_week' | 'upcoming';
  isFree?: boolean;
};

function buildDiscoverQuery(filters: DiscoveryFilters): string {
  const params = new URLSearchParams();

  if (filters.query?.trim()) {
    params.set('q', filters.query.trim());
  }
  if (filters.category) {
    params.set('category', filters.category);
  }
  if (filters.dateBucket) {
    params.set('date_bucket', filters.dateBucket);
  }
  if (typeof filters.isFree === 'boolean') {
    params.set('is_free', String(filters.isFree));
  }

  const query = params.toString();
  return query ? `?${query}` : '';
}

export async function listDiscoverableEvents(filters: DiscoveryFilters): Promise<EventDiscoveryItem[]> {
  return apiRequest<EventDiscoveryItem[]>({
    path: `/events/discover${buildDiscoverQuery(filters)}`,
    method: 'GET',
  });
}

export async function getDiscoverableEventDetail(eventId: number): Promise<EventDiscoveryDetail> {
  return apiRequest<EventDiscoveryDetail>({
    path: `/events/discover/${eventId}`,
    method: 'GET',
  });
}
