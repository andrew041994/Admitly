import { EventPriceSummary } from '../../api/events';

export function formatEventDateRange(startAt: string, endAt: string): string {
  const start = new Date(startAt);
  const end = new Date(endAt);

  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return 'Date to be announced';
  }

  const datePart = new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(start);

  const startTime = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(start);

  const endTime = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(end);

  return `${datePart} • ${startTime} - ${endTime}`;
}

export function formatVenueLabel(args: {
  venueName?: string | null;
  venueCity?: string | null;
  venueCountry?: string | null;
  customVenueName?: string | null;
  customAddressText?: string | null;
}): string {
  const name = args.venueName ?? args.customVenueName;
  const locality = [args.venueCity, args.venueCountry].filter(Boolean).join(', ');
  const fallbackAddress = args.customAddressText;

  return [name, locality].filter(Boolean).join(' • ') || fallbackAddress || 'Location TBA';
}

export function formatPriceLabel(priceSummary: EventPriceSummary | null): string | null {
  if (!priceSummary) {
    return null;
  }
  if (priceSummary.is_free) {
    return 'Free entry';
  }
  return `From ${priceSummary.currency} ${priceSummary.min_price}`;
}
