import { FormEvent, useEffect, useMemo, useState } from 'react';
import { EventCard, PublicLayout } from '../components/PublicSite';
import { listUpcomingPublicEvents, type PublicEvent } from '../lib/publicEventsApi';

export function EventsPage() {
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    listUpcomingPublicEvents()
      .then((items) => { if (active) setEvents(items); })
      .catch(() => { if (active) setError(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const visibleEvents = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return events;
    return events.filter((event) => [event.title, event.category, event.venue_name, event.custom_venue_name, event.venue_city]
      .some((value) => value?.toLocaleLowerCase().includes(needle)));
  }, [events, query]);

  function preventSubmit(event: FormEvent) {
    event.preventDefault();
  }

  return (
    <PublicLayout>
      <main className="events-page">
        <section className="events-hero">
          <div className="public-container">
            <p className="eyebrow">Explore Admitly</p>
            <h1>Find an event worth showing up for.</h1>
            <p>Browse approved, public events that are coming up.</p>
            <form className="event-search" role="search" onSubmit={preventSubmit}>
              <label htmlFor="event-search">Search events</label>
              <input id="event-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by event, category, venue, or city" />
            </form>
          </div>
        </section>
        <section className="public-section" aria-labelledby="event-list-heading">
          <div className="public-container">
            <div className="section-heading-row"><h2 id="event-list-heading">Upcoming events</h2><span>{visibleEvents.length} {visibleEvents.length === 1 ? 'event' : 'events'}</span></div>
            {loading ? <p className="public-status" role="status">Loading events…</p> : null}
            {!loading && error ? <div className="public-empty"><h3>Events could not be loaded.</h3><p>Please try again shortly.</p></div> : null}
            {!loading && !error && visibleEvents.length ? <div className="event-grid">{visibleEvents.map((event) => <EventCard event={event} key={event.id} />)}</div> : null}
            {!loading && !error && !visibleEvents.length ? <div className="public-empty"><h3>{events.length ? 'No events match that search.' : 'More events are on the way.'}</h3><p>{events.length ? 'Try another event name, category, venue, or city.' : 'Approved upcoming events will appear here as they are published.'}</p></div> : null}
          </div>
        </section>
      </main>
    </PublicLayout>
  );
}
