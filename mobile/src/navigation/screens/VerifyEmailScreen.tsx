import { useEffect, useRef, useState } from 'react';

import { ThemedButton } from '../../components/ThemedButton';
import { getErrorMessage, useSession } from '../../context/SessionContext';
import { AuthError, AuthInput, AuthLink, AuthScreenLayout, AuthSuccess } from './AuthScreenLayout';

type Props = {
  initialToken?: string;
  onGoToSignIn: () => void;
};

export function VerifyEmailScreen({ initialToken, onGoToSignIn }: Props) {
  const { user, resendVerification, verifyEmail } = useSession();
  const attemptedInitialToken = useRef(false);
  const [token, setToken] = useState(initialToken ?? '');
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submitToken(value = token) {
    const normalizedToken = value.trim();
    if (!normalizedToken || verifying) {
      if (!normalizedToken) setError('Enter the verification code from your email.');
      return;
    }
    setVerifying(true);
    setError(null);
    setSuccess(null);
    try {
      await verifyEmail(normalizedToken);
      setSuccess(user ? 'Email verified. Opening Admitly…' : 'Email verified. You can now sign in.');
    } catch (err) {
      setError(`${getErrorMessage(err)} Request a new verification email and try again.`);
    } finally {
      setVerifying(false);
    }
  }

  async function resend() {
    if (resending) return;
    setResending(true);
    setError(null);
    setSuccess(null);
    try {
      await resendVerification();
      setSuccess('If verification is still required, a new email has been sent.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setResending(false);
    }
  }

  useEffect(() => {
    if (initialToken && !attemptedInitialToken.current) {
      attemptedInitialToken.current = true;
      setToken(initialToken);
      void submitToken(initialToken);
    }
  }, [initialToken]);

  return (
    <AuthScreenLayout
      title="Verify your email"
      subtitle={user ? `We sent a verification link to ${user.email}.` : 'Open the link or enter the code from your Admitly email.'}
    >
      <AuthInput
        value={token}
        onChangeText={setToken}
        placeholder="Verification code"
        autoCapitalize="none"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
      />
      <AuthError message={error} />
      <AuthSuccess message={success} />
      <ThemedButton label="Verify email" onPress={() => submitToken()} loading={verifying} disabled={verifying || resending} />
      {user ? (
        <ThemedButton label="Resend verification email" variant="secondary" onPress={resend} loading={resending} disabled={verifying || resending} />
      ) : (
        <AuthLink label="Sign in to resend verification" onPress={onGoToSignIn} />
      )}
      <AuthLink label="Use a different account" onPress={onGoToSignIn} />
    </AuthScreenLayout>
  );
}
