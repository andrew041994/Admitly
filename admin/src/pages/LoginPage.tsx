import { type FormEvent, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { state, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requestedDestination = typeof location.state === 'object' && location.state && 'from' in location.state && typeof location.state.from === 'string' ? location.state.from : '/tickets';
  const destination = requestedDestination.startsWith('/') && !requestedDestination.startsWith('//') ? requestedDestination : '/tickets';
  const routeMessage = typeof location.state === 'object' && location.state && 'message' in location.state && typeof location.state.message === 'string' ? location.state.message : null;

  if (state === 'signed-in') return <Navigate to={destination} replace />;
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await signIn(email, password); navigate(destination, { replace: true }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card"><Link className="legal-brand" to="/">Admitly</Link><p className="eyebrow">Welcome back</p><h1>Sign in to Admitly</h1><p>Use the same account you use in the mobile app.</p>{routeMessage ? <p className="success-text" role="status">{routeMessage}</p> : null}<form onSubmit={submit} className="web-form">{error ? <p className="form-error" role="alert">{error}</p> : null}<label>Email<input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label><button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Log In'}</button></form><div className="auth-links"><Link to="/forgot-password">Forgot password?</Link><span>New to Admitly? <Link to="/signup" state={{ from: destination }}>Sign up</Link></span></div></section></main>;
}
