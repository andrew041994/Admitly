import { type FormEvent, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function SignupPage() {
  const { state, signUp } = useAuth(); const navigate = useNavigate(); const location = useLocation();
  const requestedDestination = typeof location.state === 'object' && location.state && 'from' in location.state && typeof location.state.from === 'string' ? location.state.from : '/account';
  const destination = requestedDestination.startsWith('/') && !requestedDestination.startsWith('//') ? requestedDestination : '/account';
  const [form, setForm] = useState({ name: '', email: '', password: '' }); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  if (state === 'signed-in') return <Navigate to="/tickets" replace />;
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(null); try { await signUp(form.name, form.email, form.password); navigate(destination, { replace: true }); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to create account.'); } finally { setBusy(false); } }
  return <main className="auth-page"><section className="auth-card"><Link className="legal-brand" to="/">Admitly</Link><p className="eyebrow">Create your account</p><h1>Join Admitly</h1><form className="web-form" onSubmit={submit}>{error ? <p className="form-error" role="alert">{error}</p> : null}<label>Full name<input autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label><label>Email<input type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label><label>Password<input type="password" autoComplete="new-password" minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></label><button disabled={busy}>{busy ? 'Creating account…' : 'Sign Up'}</button></form><p>Email verification is required before protected account actions. Event creators must be 18+, with identity and age verified separately before an event can be approved.</p><Link to="/login">Already have an account? Log in</Link></section></main>;
}
