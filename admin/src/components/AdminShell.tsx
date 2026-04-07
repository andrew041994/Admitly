import { NavLink, Outlet } from 'react-router-dom';

export function AdminShell() {
  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div>
          <p className="admin-kicker">Admitly Internal</p>
          <h1>Admin Console</h1>
        </div>
      </header>
      <div className="admin-body">
        <nav className="admin-nav" aria-label="Admin navigation">
          <NavLink
            to="/support"
            className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
          >
            Support
          </NavLink>

          <NavLink
            to="/finance"
            className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
          >
            Finance
          </NavLink>
        </nav>
        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
