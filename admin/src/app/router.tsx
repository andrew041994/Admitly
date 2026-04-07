import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminShell } from '../components/AdminShell';
import { SupportPage } from '../pages/SupportPage';
import { FinancePage } from '../pages/FinancePage';
import { CheckInPage } from '../pages/CheckInPage';
import { MessagingPage } from '../pages/MessagingPage';
import { IntegrationsPage } from '../pages/IntegrationsPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AdminShell />}>
        <Route index element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/finance" element={<FinancePage />} />
        <Route path="/check-in" element={<CheckInPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/messaging" element={<MessagingPage />} />
      </Route>
    </Routes>
  );
}
