export type NotificationDestination =
  | { screen: 'TicketDetail'; params: { ticketId: number } }
  | { screen: 'MyTickets'; params?: undefined }
  | { screen: 'EventDetail'; params: { eventId: number } };

function positiveInteger(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function getNotificationDestination(input: {
  route_key?: unknown;
  routeKey?: unknown;
  route_params?: unknown;
  ticket_id?: unknown;
  ticketId?: unknown;
  event_id?: unknown;
  eventId?: unknown;
}): NotificationDestination | null {
  const routeKey = input.route_key ?? input.routeKey;
  const routeParams = input.route_params && typeof input.route_params === 'object'
    ? input.route_params as Record<string, unknown>
    : {};
  const ticketId = positiveInteger(routeParams.ticket_id ?? input.ticket_id ?? input.ticketId);
  const eventId = positiveInteger(routeParams.event_id ?? input.event_id ?? input.eventId);
  if (routeKey === 'ticket' && ticketId) return { screen: 'TicketDetail', params: { ticketId } };
  if (routeKey === 'transfers' || routeKey === 'wallet') return { screen: 'MyTickets' };
  if (routeKey === 'event' && eventId) return { screen: 'EventDetail', params: { eventId } };
  return null;
}
