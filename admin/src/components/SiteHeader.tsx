import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function BrandMark() {
  return (
    <Link className="public-brand" to="/" aria-label="Admitly home">
      <span className="brand-symbol" aria-hidden="true">A</span>
      <span>Admitly</span>
    </Link>
  );
}

export function AuthenticatedHeader() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  async function handleSignOut() {
    await signOut();
    navigate('/login', { replace: true, state: { from: location.pathname } });
  }

  return (
    <>
      <header className="user-header">
        <div className="user-header-inner">
          <BrandMark />
          <nav aria-label="Account navigation">
            <NavLink to="/events">Discover</NavLink>
            <NavLink to="/tickets">My Tickets</NavLink>
            <NavLink to="/my-events">My Events</NavLink>
            <NavLink to="/notifications">Notifications</NavLink>
            <NavLink to="/account">Account</NavLink>
          </nav>
          <div className="user-actions">
            <NavLink className="button" to="/create-event">Create Event</NavLink>
            {user?.is_admin ? <NavLink to="/admin">Admin Dashboard</NavLink> : null}
            <button className="button-link" onClick={() => void handleSignOut()}>Log Out</button>
          </div>
        </div>
      </header>
      {user?.requires_email_verification ? (
        <div className="verification-banner" role="status">
          Verify your email to use protected Admitly features. <NavLink to="/account">Resend verification</NavLink>
        </div>
      ) : null}
    </>
  );
}
