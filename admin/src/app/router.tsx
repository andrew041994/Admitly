import { Navigate, Route, Routes } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { AdminShell } from '../components/AdminShell';
import { validateAdminSession } from '../lib/authApi';
import { getAdminSession } from '../lib/authSession';
import { SupportPage } from '../pages/SupportPage';
import { FinancePage } from '../pages/FinancePage';
import { CheckInPage } from '../pages/CheckInPage';
import { MessagingPage } from '../pages/MessagingPage';
import { IntegrationsPage } from '../pages/IntegrationsPage';
import { EventApprovalsPage } from '../pages/EventApprovalsPage';
import { LoginPage } from '../pages/LoginPage';
import { ResetPasswordRedirectPage } from '../pages/ResetPasswordRedirectPage';
import { VerifyEmailRedirectPage } from '../pages/VerifyEmailRedirectPage';

function RequireAdmin() {
  const session = getAdminSession();
  const [validationState, setValidationState] = useState<'checking' | 'allowed' | 'denied'>(session ? 'checking' : 'denied');

  useEffect(() => {
    if (!session) return;
    let active = true;
    validateAdminSession()
      .then(() => { if (active) setValidationState('allowed'); })
      .catch(() => { if (active) setValidationState('denied'); });
    return () => { active = false; };
  }, []);

  if (!session) return <Navigate to="/login" replace />;
  if (!session.user.is_admin) return <Navigate to="/login" replace state={{ message: 'Admin access required.' }} />;
  if (validationState === 'checking') return <main className="login-page"><p>Validating admin session…</p></main>;
  if (validationState === 'denied') return <Navigate to="/login" replace state={{ message: 'Admin access required.' }} />;
  return <AdminShell />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/reset-password" element={<ResetPasswordRedirectPage />} />
      <Route path="/verify-email" element={<VerifyEmailRedirectPage />} />
      <Route element={<RequireAdmin />}>
        <Route index element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/finance" element={<FinancePage />} />
        <Route path="/check-in" element={<CheckInPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/messaging" element={<MessagingPage />} />
        <Route path="/event-approvals" element={<EventApprovalsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/support" replace />} />
    </Routes>
  );
}
