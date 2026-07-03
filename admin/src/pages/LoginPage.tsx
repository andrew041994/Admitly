import { FormEvent, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { loginAdmin } from '../lib/authApi';
import { getAdminSession } from '../lib/authSession';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const routeMessage = typeof location.state === 'object' && location.state && 'message' in location.state ? String(location.state.message) : null;
  const [error, setError] = useState<string | null>(routeMessage);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (getAdminSession()) return <Navigate to="/support" replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await loginAdmin(email, password);
      navigate('/support', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <p className="admin-kicker">Admitly Internal</p>
        <h1>Admin sign in</h1>
        {error ? <p className="error-text">{error}</p> : null}
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </main>
  );
}
