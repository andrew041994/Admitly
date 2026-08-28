import { Outlet } from 'react-router-dom';
import { AuthenticatedHeader } from './SiteHeader';

export function UserShell() {
  return <div className="user-app"><AuthenticatedHeader /><main className="user-main"><Outlet /></main></div>;
}
