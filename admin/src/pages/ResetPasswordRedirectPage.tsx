import { useEffect, useMemo } from 'react';

export function ResetPasswordRedirectPage() {
  const token = useMemo(() => new URLSearchParams(window.location.search).get('token') ?? '', []);
  const deepLink = useMemo(() => `admitly://reset-password?token=${encodeURIComponent(token)}`, [token]);

  function openAdmitly() {
    window.location.href = deepLink;
  }

  useEffect(() => {
    openAdmitly();
  }, [deepLink]);

  return (
    <main className="reset-redirect-page">
      <section className="reset-redirect-card" aria-labelledby="reset-redirect-title">
        <p className="admin-kicker">Admitly password reset</p>
        <h1 id="reset-redirect-title">Open Admitly to reset your password</h1>
        <p>
          If Admitly does not open automatically, copy this reset code and paste it into the Reset Password screen in the app.
        </p>
        <label className="reset-code-label" htmlFor="reset-code">
          Reset code
        </label>
        <input id="reset-code" className="reset-code-box" value={token} readOnly onFocus={(event) => event.currentTarget.select()} />
        <button type="button" onClick={openAdmitly}>
          Open Admitly
        </button>
      </section>
    </main>
  );
}
