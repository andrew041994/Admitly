import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { BrandMark } from './PublicSite';

export function UserShell() {
  const { user, signOut } = useAuth(); const navigate = useNavigate(); const location = useLocation();
  return <div className="user-app"><header className="user-header"><div className="user-header-inner"><BrandMark /><nav aria-label="Account navigation"><NavLink to="/events">Discover</NavLink><NavLink to="/tickets">My Tickets</NavLink><NavLink to="/my-events">My Events</NavLink><NavLink to="/notifications">Notifications</NavLink><NavLink to="/account">Account</NavLink></nav><div className="user-actions"><NavLink className="button button-small" to="/create-event">Create Event</NavLink>{user?.is_admin ? <NavLink to="/admin">Admin Dashboard</NavLink> : null}<button className="button-link" onClick={() => void signOut().then(() => navigate('/login', { replace: true, state: { from: location.pathname } }))}>Log Out</button></div></div></header>{user?.requires_email_verification ? <div className="verification-banner" role="status">Verify your email to use protected Admitly features. <NavLink to="/account">Resend verification</NavLink></div> : null}<main className="user-main"><Outlet /></main></div>;
}
