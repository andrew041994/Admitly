import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminShell } from '../components/AdminShell';
import { getAdminSession } from '../lib/authSession';
import { SupportPage } from '../pages/SupportPage';
import { FinancePage } from '../pages/FinancePage';
import { CheckInPage } from '../pages/CheckInPage';
import { MessagingPage } from '../pages/MessagingPage';
import { IntegrationsPage } from '../pages/IntegrationsPage';
import { EventApprovalsPage } from '../pages/EventApprovalsPage';
import { LoginPage } from '../pages/LoginPage';

function RequireAdmin() {
  const session = getAdminSession();
  if (!session) return <Navigate to="/login" replace />;
  if (!session.user.is_admin) return <Navigate to="/login" replace state={{ message: 'Admin access required.' }} />;
  return <AdminShell />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
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
