import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { clearAdminSession, getAdminSession } from '../lib/authSession';

export function AdminShell() {
  const navigate = useNavigate();
  const [authMessage, setAuthMessage] = useState<string | null>(null);
  const session = getAdminSession();

  useEffect(() => {
    function handleAuthRequired(event: Event) {
      const detail = event instanceof CustomEvent && typeof event.detail === 'string' ? event.detail : 'Admin access required.';
      setAuthMessage(detail);
      navigate('/login', { replace: true, state: { message: detail } });
    }
    window.addEventListener('admin-auth-required', handleAuthRequired);
    return () => window.removeEventListener('admin-auth-required', handleAuthRequired);
  }, [navigate]);

  function signOut() {
    clearAdminSession();
    navigate('/login', { replace: true });
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <p className="admin-kicker">Admitly Internal</p>
          <h1>Admin Console</h1>
          {authMessage ? <p className="error-text">{authMessage}</p> : null}
        </div>
        <div className="admin-user-controls">
          <span>{session?.user.email}</span>
          <button type="button" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <div className="admin-body">
        <nav className="admin-nav" aria-label="Admin navigation">
          <NavLink to="/support" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Support</NavLink>
          <NavLink to="/finance" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Finance</NavLink>
          <NavLink to="/messaging" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Messaging</NavLink>
          <NavLink to="/check-in" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Check-in</NavLink>
          <NavLink to="/integrations" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Integrations</NavLink>
          <NavLink to="/event-approvals" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Event approvals</NavLink>
        </nav>
        <main className="admin-main"><Outlet /></main>
      </div>
    </div>
  );
}
