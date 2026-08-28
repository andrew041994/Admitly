import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  EventCard,
  PublicLayout,
} from '../components/PublicSite';
import { listUpcomingPublicEvents, type PublicEvent } from '../lib/publicEventsApi';

const attendeeSteps = [
  ['01', 'Discover an event', 'Explore upcoming events and find the right experience.'],
  ['02', 'Choose your ticket', 'Review ticket options and complete the available checkout flow.'],
  ['03', 'Receive your ticket', 'Keep your ticket available in Admitly after payment is confirmed.'],
  ['04', 'Present it for admission', 'Show the ticket QR code at the event check-in.'],
];

const creatorSteps = [
  'Create your event from your Admitly account.',
  'Securely submit account age and identity verification if you have not already been verified.',
  'Admitly reviews the event before it can be approved and published.',
  'Manage ticket availability and your event from Admitly.',
  'Run your event and use Admitly’s check-in tools.',
  'Admitly processes payout within 5 business days after the event concludes, less applicable fees and subject to reconciliation, security, and legal review.',
];

const trustItems = [
  ['Ticket ownership', 'Tickets stay connected to the current Admitly owner and order record.'],
  ['Ticket transfers', 'Send a ticket through the supported email-based transfer flow.'],
  ['QR check-in', 'Present ticket QR codes for event admission and duplicate-scan checks.'],
  ['Event management', 'Creators manage their events while assigned staff use scoped operational tools.'],
  ['Canceled-event refunds', 'Canceled events are refund eligible, subject to applicable law. Rescheduled tickets remain valid.'],
];

export function LandingPage() {
  const [events, setEvents] = useState<PublicEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let active = true;
    listUpcomingPublicEvents()
      .then((items) => {
        if (active) setEvents(items.slice(0, 6));
      })
      .catch(() => {
        if (active) setLoadFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  return (
    <PublicLayout>
      <main>
        <section className="hero-section">
          <div className="public-container hero-grid">
            <div className="hero-copy">
              <p className="eyebrow">Events, made simpler</p>
              <h1>Find your next event. <span>Or create one.</span></h1>
              <p className="hero-lede">Admitly makes it simple to discover events, choose tickets, and manage your own events from one place.</p>
              <div className="cta-row">
                <Link className="button" to="/events">Browse Events</Link>
                <Link className="button button-secondary" to="/create-event">Create an Event</Link>
              </div>
              <p className="app-handoff-note">Use Admitly on the web or continue with the supported mobile app.</p>
            </div>
            <div className="hero-art" aria-label="A preview of an Admitly event ticket">
              <div className="hero-orbit hero-orbit-one" />
              <div className="hero-orbit hero-orbit-two" />
              <article className="ticket-preview">
                <div className="ticket-preview-top">
                  <span className="ticket-chip">YOUR NEXT EVENT</span>
                  <span className="ticket-dot" />
                </div>
                <div className="ticket-stage" aria-hidden="true">
                  <span /><span /><span /><span /><span />
                </div>
                <h2>Good nights start here.</h2>
                <div className="ticket-meta"><span>Discover</span><span>Choose</span><span>Admit</span></div>
                <div className="ticket-code" aria-hidden="true">|||| ||| || |||| | |||</div>
              </article>
            </div>
          </div>
        </section>

        <section className="public-section discovery-section" aria-labelledby="upcoming-heading">
          <div className="public-container">
            <div className="section-heading-row">
              <div>
                <p className="eyebrow">What’s happening</p>
                <h2 id="upcoming-heading">Upcoming events</h2>
              </div>
              <Link className="text-link" to="/events">Browse All Events <span aria-hidden="true">→</span></Link>
            </div>
            {loading ? <p className="public-status" role="status">Loading upcoming events…</p> : null}
            {!loading && events.length ? (
              <div className="event-grid">{events.map((event) => <EventCard event={event} key={event.id} />)}</div>
            ) : null}
            {!loading && !events.length ? (
              <div className="public-empty">
                <h3>{loadFailed ? 'Events are taking a moment to load.' : 'More events are on the way.'}</h3>
                <p>{loadFailed ? 'Visit the full event listing to try again.' : 'Approved upcoming events will appear here as they are published.'}</p>
                <Link className="text-link" to="/events">Browse events</Link>
              </div>
            ) : null}
          </div>
        </section>

        <section className="public-section steps-section" aria-labelledby="attendee-heading">
          <div className="public-container">
            <p className="eyebrow">For attendees</p>
            <h2 id="attendee-heading">From discovery to the door</h2>
            <div className="steps-grid">
              {attendeeSteps.map(([number, title, body]) => (
                <article className="step-card" key={number}>
                  <span>{number}</span><h3>{title}</h3><p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="public-section creator-section" aria-labelledby="creator-heading">
          <div className="public-container creator-grid">
            <div>
              <p className="eyebrow">For event creators</p>
              <h2 id="creator-heading">Your event, thoughtfully supported.</h2>
              <p>Create an event from your Admitly account, complete a straightforward review, and manage ticketing through the event.</p>
              <Link className="button" to="/create-event">Create an Event</Link>
              <p className="fine-print">Creators must be 18+. A government-issued ID may be uploaded securely for temporary, private review and is deleted through Admitly’s verification cleanup process after review. Verified creator accounts generally do not need to resubmit ID for each event.</p>
            </div>
            <ol className="creator-steps">
              {creatorSteps.map((step, index) => <li key={step}><span>{index + 1}</span><p>{step}</p></li>)}
            </ol>
          </div>
        </section>

        <section className="public-section trust-section" aria-labelledby="trust-heading">
          <div className="public-container">
            <p className="eyebrow">Built for the whole event</p>
            <h2 id="trust-heading">The essentials, connected.</h2>
            <div className="trust-grid">
              {trustItems.map(([title, body], index) => (
                <article key={title}><span aria-hidden="true">0{index + 1}</span><h3>{title}</h3><p>{body}</p></article>
              ))}
            </div>
          </div>
        </section>

        <section className="final-cta">
          <div className="public-container final-cta-inner">
            <div><p className="eyebrow">Your next event starts here</p><h2>Ready when you are.</h2></div>
            <div className="cta-row">
              <Link className="button button-light" to="/events">Browse Events</Link>
              <Link className="button button-outline-light" to="/create-event">Create an Event</Link>
            </div>
          </div>
        </section>
      </main>
    </PublicLayout>
  );
}
