import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { attendeeLoginUrl, eventVenue, formatEventDate, PublicLayout } from '../components/PublicSite';
import { getPublicEvent, type PublicEventDetail } from '../lib/publicEventsApi';

function tierPrice(amountValue: string, currency: string) {
  const amount = Number(amountValue);
  if (amount === 0) return 'Free';
  if (!Number.isFinite(amount)) return `${currency} ${amountValue}`;
  try {
    return new Intl.NumberFormat('en-GY', { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount);
  } catch {
    return `${currency} ${amountValue}`;
  }
}

export function EventDetailPage() {
  const { eventId } = useParams();
  const numericEventId = Number(eventId);
  const [event, setEvent] = useState<PublicEventDetail | null>(null);
  const [failed, setFailed] = useState(!Number.isInteger(numericEventId) || numericEventId <= 0);

  useEffect(() => {
    if (!Number.isInteger(numericEventId) || numericEventId <= 0) return;
    let active = true;
    getPublicEvent(numericEventId)
      .then((item) => { if (active) setEvent(item); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [numericEventId]);

  return (
    <PublicLayout>
      <main className="event-detail-page">
        <div className="public-container">
          <Link className="back-link" to="/events">← All events</Link>
          {!event && !failed ? <p className="public-status" role="status">Loading event…</p> : null}
          {failed ? <div className="public-empty"><h1>Event not found.</h1><p>This event may no longer be publicly available.</p><Link className="button" to="/events">Browse Events</Link></div> : null}
          {event ? (
            <article className="event-detail">
              <div className="event-detail-cover">
                {event.cover_image_url ? <img src={event.cover_image_url} alt={`${event.title} event cover`} /> : <span aria-hidden="true">Admitly</span>}
              </div>
              <div className="event-detail-grid">
                <div className="event-detail-copy">
                  {event.category ? <p className="eyebrow">{event.category}</p> : null}
                  <h1>{event.title}</h1>
                  {event.organizer_name ? <p className="event-organizer">Presented by {event.organizer_name}</p> : null}
                  <div className="event-facts">
                    <p><strong>Date and time</strong><span>{formatEventDate(event.start_at)}</span></p>
                    <p><strong>Location</strong><span>{eventVenue(event)}</span></p>
                  </div>
                  <section aria-labelledby="about-event"><h2 id="about-event">About this event</h2><p>{event.long_description || event.short_description || 'More event details will be available soon.'}</p></section>
                </div>
                <aside className="ticket-panel" aria-labelledby="tickets-heading">
                  <h2 id="tickets-heading">Tickets</h2>
                  {event.ticket_tiers.filter((tier) => tier.is_active).length ? (
                    <ul>
                      {event.ticket_tiers.filter((tier) => tier.is_active).map((tier) => (
                        <li key={tier.id}><div><strong>{tier.name}</strong>{tier.description ? <span>{tier.description}</span> : null}</div><span>{tierPrice(tier.price_amount, tier.currency)}</span></li>
                      ))}
                    </ul>
                  ) : <p>Ticket details are not currently available.</p>}
                  <a className="button" href={attendeeLoginUrl}>Continue in the Admitly app</a>
                  <p className="fine-print">Sign in to access the ticket and checkout options currently available for this event.</p>
                </aside>
              </div>
            </article>
          ) : null}
        </div>
      </main>
    </PublicLayout>
  );
}
