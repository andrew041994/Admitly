import { useState } from 'react';

import { ThemedButton } from '../../components/ThemedButton';
import { getErrorMessage, useSession } from '../../context/SessionContext';
import { AuthError, AuthInput, AuthLink, AuthScreenLayout, AuthSuccess } from './AuthScreenLayout';

type ForgotPasswordScreenProps = {
  onGoToSignIn: () => void;
  onGoToResetPassword: () => void;
};

export function ForgotPasswordScreen({ onGoToSignIn, onGoToResetPassword }: ForgotPasswordScreenProps) {
  const { requestPasswordReset } = useSession();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit() {
    if (!email.trim()) {
      setError('Please enter your email.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      await requestPasswordReset(email);
      setSuccess('If an account exists for this email, reset instructions have been sent.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScreenLayout title="Forgot Password" subtitle="We will help you get back in quickly.">
      <AuthInput
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        keyboardType="email-address"
        autoComplete="email"
        textContentType="emailAddress"
      />
      <AuthError message={error} />
      <AuthSuccess message={success} />
      <ThemedButton label="Send reset link" onPress={handleSubmit} loading={submitting} disabled={submitting} />
      <AuthLink label="Have a reset token? Reset password" onPress={onGoToResetPassword} />
      <AuthLink label="Back to sign in" onPress={onGoToSignIn} />
    </AuthScreenLayout>
  );
}
