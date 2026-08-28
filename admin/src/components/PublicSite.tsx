import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import type { PublicEvent } from '../lib/publicEventsApi';
import { AuthenticatedHeader, BrandMark } from './SiteHeader';

export const attendeeLoginUrl = 'admitly://sign-in';
export const attendeeSignupUrl = 'admitly://sign-up';

type PublicLayoutProps = {
  children: ReactNode;
};

export function PublicHeader() {
  const { state } = useAuth();

  if (state === 'signed-in') return <AuthenticatedHeader />;
  if (state === 'booting') {
    return (
      <header className="public-header">
        <div className="public-container public-nav-row">
          <BrandMark />
          <span className="public-auth-restoring" role="status">Restoring your session…</span>
        </div>
      </header>
    );
  }

  return (
    <header className="public-header">
      <div className="public-container public-nav-row">
        <BrandMark />
        <nav className="public-nav" aria-label="Primary navigation">
          <Link to="/events">Browse Events</Link>
          <Link to="/create-event">Create an Event</Link>
          <Link to="/login">Log In</Link>
          <Link className="button button-small" to="/signup">Sign Up</Link>
        </nav>
        <details className="mobile-menu">
          <summary aria-label="Open navigation menu">Menu</summary>
          <nav aria-label="Mobile navigation">
            <Link to="/events">Browse Events</Link>
            <Link to="/create-event">Create an Event</Link>
            <Link to="/login">Log In</Link>
            <Link to="/signup">Sign Up</Link>
          </nav>
        </details>
      </div>
    </header>
  );
}

export function PublicFooter() {
  const { state } = useAuth();
  const signedIn = state === 'signed-in';

  return (
    <footer className="public-footer">
      <div className="public-container footer-grid">
        <div>
          <BrandMark />
          <p>Find events and manage tickets in one place.</p>
        </div>
        <nav aria-label="Explore">
          <strong>Explore</strong>
          <Link to="/events">Browse Events</Link>
          {signedIn ? (
            <>
              <Link to="/tickets">My Tickets</Link>
              <Link to="/my-events">My Events</Link>
              <Link to="/account">Account</Link>
            </>
          ) : state === 'signed-out' ? (
            <>
              <Link to="/login">Log In</Link>
              <Link to="/signup">Sign Up</Link>
            </>
          ) : null}
          <Link to="/terms#questions">Support &amp; contact</Link>
        </nav>
        <nav aria-label="Legal policies">
          <strong>Policies</strong>
          <Link to="/privacy">Privacy Policy</Link>
          <Link to="/refund-policy">Refund Policy</Link>
          <Link to="/terms">Terms of Service</Link>
          <Link to="/organizer-terms">Organizer Terms</Link>
          <Link to="/buyer-terms">Buyer Terms</Link>
        </nav>
      </div>
      <div className="public-container footer-bottom">
        <span>© {new Date().getFullYear()} Admitly</span>
        <a href={attendeeLoginUrl}>Open in App</a>
      </div>
    </footer>
  );
}

export function PublicLayout({ children }: PublicLayoutProps) {
  return (
    <div className="public-site">
      <PublicHeader />
      {children}
      <PublicFooter />
    </div>
  );
}

export function formatEventDate(value: string) {
  return new Intl.DateTimeFormat('en-GY', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

export function formatEventPrice(event: PublicEvent) {
  if (!event.price_summary) return 'Ticket details in the app';
  if (event.price_summary.is_free) return 'Free';
  const amount = Number(event.price_summary.min_price);
  if (!Number.isFinite(amount)) return `From ${event.price_summary.currency} ${event.price_summary.min_price}`;
  try {
    return `From ${new Intl.NumberFormat('en-GY', {
      style: 'currency',
      currency: event.price_summary.currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(amount)}`;
  } catch {
    return `From ${event.price_summary.currency} ${event.price_summary.min_price}`;
  }
}

export function eventVenue(event: PublicEvent) {
  return event.venue_name || event.custom_venue_name || event.venue_city || 'Venue details available soon';
}

export function EventCard({ event }: { event: PublicEvent }) {
  return (
    <article className="event-card">
      <Link className="event-card-image" to={`/events/${event.id}`} aria-label={`View ${event.title}`}>
        {event.cover_image_url ? (
          <img src={event.cover_image_url} alt={`${event.title} event cover`} loading="lazy" />
        ) : (
          <span aria-hidden="true">Admitly</span>
        )}
      </Link>
      <div className="event-card-body">
        {event.category ? <p className="eyebrow">{event.category}</p> : null}
        <h3><Link to={`/events/${event.id}`}>{event.title}</Link></h3>
        <p className="event-date">{formatEventDate(event.start_at)}</p>
        <p className="event-location">{eventVenue(event)}</p>
        <div className="event-card-footer">
          <strong>{formatEventPrice(event)}</strong>
          <Link to={`/events/${event.id}`}>View event <span aria-hidden="true">→</span></Link>
        </div>
      </div>
    </article>
  );
}
