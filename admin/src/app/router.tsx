import { useEffect, useState } from 'react';
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { AdminShell } from '../components/AdminShell';
import { UserShell } from '../components/UserShell';
import { validateAdminSession } from '../lib/authApi';
import { AccountPage } from '../pages/AccountPage';
import { CheckInPage } from '../pages/CheckInPage';
import { CreateEventPage } from '../pages/CreateEventPage';
import { EventApprovalsPage } from '../pages/EventApprovalsPage';
import { EventDetailPage } from '../pages/EventDetailPage';
import { EventsPage } from '../pages/EventsPage';
import { FinancePage } from '../pages/FinancePage';
import { ForgotPasswordPage } from '../pages/ForgotPasswordPage';
import { IntegrationsPage } from '../pages/IntegrationsPage';
import { LandingPage } from '../pages/LandingPage';
import { LegalPage } from '../pages/LegalPage';
import { LoginPage } from '../pages/LoginPage';
import { ManageEventPage } from '../pages/ManageEventPage';
import { MaterialChangePage } from '../pages/MaterialChangePage';
import { MessagingPage } from '../pages/MessagingPage';
import { MyEventsPage } from '../pages/MyEventsPage';
import { NotificationsPage } from '../pages/NotificationsPage';
import { ResetPasswordRedirectPage } from '../pages/ResetPasswordRedirectPage';
import { SignupPage } from '../pages/SignupPage';
import { SupportPage } from '../pages/SupportPage';
import { TicketDetailPage } from '../pages/TicketDetailPage';
import { TicketsPage } from '../pages/TicketsPage';
import { TransfersPage } from '../pages/TransfersPage';
import { VerifyEmailRedirectPage } from '../pages/VerifyEmailRedirectPage';

function RequireAuth() {
  const { state } = useAuth(); const location = useLocation();
  if (state === 'booting') return <main className="route-loading" role="status">Restoring your Admitly session…</main>;
  if (state === 'signed-out') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

function RequireAdmin() {
  const { state, user } = useAuth(); const location = useLocation();
  const [validation, setValidation] = useState<'idle' | 'checking' | 'allowed' | 'denied'>('idle');
  useEffect(() => {
    if (state !== 'signed-in' || !user?.is_admin) { setValidation('denied'); return; }
    let active = true; setValidation('checking');
    validateAdminSession().then(() => { if (active) setValidation('allowed'); }).catch(() => { if (active) setValidation('denied'); });
    return () => { active = false; };
  }, [state, user?.id, user?.is_admin]);
  if (state === 'booting' || validation === 'idle' || validation === 'checking') return <main className="route-loading" role="status">Validating admin access…</main>;
  if (state === 'signed-out') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!user?.is_admin || validation === 'denied') return <main className="auth-page"><section className="auth-card"><h1>Admin access required</h1><p>Your signed-in account is not authorized for the Admitly admin console.</p><a href="/tickets">Return to Admitly</a></section></main>;
  return <AdminShell />;
}

export function AppRouter() {
  return <Routes>
    <Route index element={<LandingPage />} />
    <Route path="/events" element={<EventsPage />} />
    <Route path="/events/:eventId" element={<EventDetailPage />} />
    <Route path="/login" element={<LoginPage />} />
    <Route path="/signup" element={<SignupPage />} />
    <Route path="/forgot-password" element={<ForgotPasswordPage />} />
    <Route path="/reset-password" element={<ResetPasswordRedirectPage />} />
    <Route path="/verify-email" element={<VerifyEmailRedirectPage />} />
    <Route path="/privacy" element={<LegalPage />} /><Route path="/refund-policy" element={<LegalPage />} /><Route path="/terms" element={<LegalPage />} /><Route path="/organizer-terms" element={<LegalPage />} /><Route path="/buyer-terms" element={<LegalPage />} />
    <Route element={<RequireAuth />}>
      <Route element={<UserShell />}>
        <Route path="/app" element={<Navigate to="/tickets" replace />} />
        <Route path="/tickets" element={<TicketsPage />} /><Route path="/tickets/:ticketId" element={<TicketDetailPage />} /><Route path="/transfers" element={<TransfersPage />} />
        <Route path="/notifications" element={<NotificationsPage />} /><Route path="/account" element={<AccountPage />} />
        <Route path="/create-event" element={<CreateEventPage />} /><Route path="/my-events" element={<MyEventsPage />} />
        <Route path="/my-events/:eventId" element={<ManageEventPage />} /><Route path="/my-events/:eventId/material-change" element={<MaterialChangePage />} />
      </Route>
    </Route>
    <Route path="/admin" element={<RequireAdmin />}>
      <Route index element={<Navigate to="support" replace />} />
      <Route path="support" element={<SupportPage />} /><Route path="finance" element={<FinancePage />} /><Route path="check-in" element={<CheckInPage />} /><Route path="integrations" element={<IntegrationsPage />} /><Route path="messaging" element={<MessagingPage />} /><Route path="event-approvals" element={<EventApprovalsPage />} />
    </Route>
    {['support', 'finance', 'check-in', 'integrations', 'messaging', 'event-approvals'].map((path) => <Route key={path} path={`/${path}`} element={<Navigate to={`/admin/${path}`} replace />} />)}
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
