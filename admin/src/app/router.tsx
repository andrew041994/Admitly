import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminShell } from '../components/AdminShell';
import { SupportPage } from '../pages/SupportPage';
import { FinancePage } from '../pages/FinancePage';
import { CheckInPage } from '../pages/CheckInPage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AdminShell />}>
        <Route index element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/finance" element={<FinancePage />} />
        <Route path="/check-in" element={<CheckInPage />} />
      </Route>
    </Routes>
  );
}
