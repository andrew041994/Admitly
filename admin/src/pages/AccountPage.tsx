import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { requestVerification } from '../lib/authApi';
import { changePassword, getAccount, updateProfile, type AccountProfile } from '../lib/userApi';

export function AccountPage() {
  const { user, refreshUser, signOut, signOutAll } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [name, setName] = useState('');
  const [passwords, setPasswords] = useState({ current: '', next: '' });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAccount()
      .then((result) => { setProfile(result); setName(result.full_name); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'Account could not be loaded.'));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      await updateProfile(name); await refreshUser(); setMessage('Profile updated.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to update profile.'); }
  }

  async function security(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      await changePassword(passwords.current, passwords.next);
      await signOut();
      navigate('/login', { replace: true, state: { message: 'Password changed. Sign in again on this device.' } });
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to change password.'); }
  }

  async function allDevices() {
    if (!window.confirm('Log out every Admitly session on all devices?')) return;
    setError(null);
    try {
      await signOutAll();
      navigate('/login', { replace: true, state: { message: 'All devices have been logged out.' } });
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to log out all devices.'); }
  }

  const creatorVerified = profile?.creator_age_identity_verification_status === 'verified';
  return (
    <section className="user-page">
      <p className="eyebrow">Your account</p><h1>Account</h1>
      {message ? <p className="success-text" role="status">{message}</p> : null}
      {error ? <p className="form-error" role="alert">{error}</p> : null}
      {profile ? <div className="account-grid">
        <form className="panel web-form" onSubmit={save}>
          <h2>Profile</h2>
          <label>Full name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
          <label>Email<input value={profile.email} disabled /></label>
          <p>Email status: <strong>{profile.is_verified ? 'Verified' : 'Verification required'}</strong></p>
          {!profile.is_verified ? <button type="button" onClick={() => void requestVerification(profile.email).then(() => setMessage('Verification instructions requested.')).catch((reason) => setError(reason.message))}>Resend verification</button> : null}
          <h3>Event creator verification</h3>
          <p>Age verification: <strong>{creatorVerified ? 'Verified' : 'Required'}</strong></p>
          <p>{creatorVerified
            ? 'Your age has been verified. You do not need to submit ID again for future events unless Admitly asks you to reverify.'
            : 'Age verification is required before your event can be approved. You can securely submit an ID from Create Event while continuing to work on your draft.'}</p>
          <button>Save profile</button>
        </form>
        <form className="panel web-form" onSubmit={security}>
          <h2>Security</h2><p>Changing your password signs out every Admitly session, including this device.</p>
          <label>Current password<input type="password" autoComplete="current-password" value={passwords.current} onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} required /></label>
          <label>New password<input type="password" autoComplete="new-password" minLength={8} value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} required /></label>
          <button>Change password and sign out</button>
          <button className="danger-button" type="button" onClick={() => void allDevices()}>Log out all devices</button>
        </form>
        <aside className="panel"><h2>Activity</h2><p>{profile.my_tickets_count} tickets</p><p>{profile.my_events_count} events created</p><p>{profile.staff_events_count} staff assignments</p>{user?.is_admin ? <p><strong>Admin access enabled</strong></p> : null}</aside>
      </div> : <p role="status">Loading account…</p>}
    </section>
  );
}
