import { useEffect, useMemo } from 'react';

export function VerifyEmailRedirectPage() {
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') ?? '', []);
  const deepLink = useMemo(() => `admitly://verify-email?token=${encodeURIComponent(token)}`, [token]);

  function openAdmitly() {
    window.location.href = deepLink;
  }

  useEffect(() => {
    openAdmitly();
  }, [deepLink]);

  return (
    <main className="reset-redirect-page">
      <section className="reset-redirect-card" aria-labelledby="verify-email-title">
        <p className="admin-kicker">Admitly email verification</p>
        <h1 id="verify-email-title">Open Admitly to verify your email</h1>
        <p>If Admitly does not open automatically, copy this verification code and paste it into the Verify Email screen.</p>
        <label className="reset-code-label" htmlFor="verification-code">Verification code</label>
        <input id="verification-code" className="reset-code-box" value={token} readOnly onFocus={(event) => event.currentTarget.select()} />
        <button type="button" onClick={openAdmitly}>Open Admitly</button>
      </section>
    </main>
  );
}
