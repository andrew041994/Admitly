import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminShell } from '../components/AdminShell';
import { SupportPage } from '../pages/SupportPage';
import { FinancePage } from '../pages/FinancePage';

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AdminShell />}>
        <Route index element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/finance" element={<FinancePage />} />
      </Route>
    </Routes>
  );
}
