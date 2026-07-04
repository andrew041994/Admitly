import { useEffect, useRef, useState } from 'react';
import { Text, TouchableOpacity } from 'react-native';

import { ThemedButton } from '../../components/ThemedButton';
import { getErrorMessage, useSession } from '../../context/SessionContext';
import { theme } from '../../theme';
import { AuthError, AuthInput, AuthLink, AuthScreenLayout, AuthSuccess } from './AuthScreenLayout';

type ResetPasswordScreenProps = {
  initialToken?: string;
  onGoToSignIn: () => void;
};

export function ResetPasswordScreen({ initialToken, onGoToSignIn }: ResetPasswordScreenProps) {
  const { resetPassword } = useSession();
  const hasEditedToken = useRef(false);
  const [token, setToken] = useState(initialToken ?? '');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (initialToken && !hasEditedToken.current) {
      setToken(initialToken);
    }
  }, [initialToken]);

  function handleTokenChange(value: string) {
    hasEditedToken.current = true;
    setToken(value);
  }

  async function handleSubmit() {
    if (!token.trim() || !newPassword || !confirmPassword) {
      setError('Please complete all fields.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      await resetPassword(token, newPassword);
      setSuccess('Password reset successful. You can now sign in with your new password.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScreenLayout title="Reset Password" subtitle="Enter your reset token and choose a new password.">
      <AuthInput
        value={token}
        onChangeText={handleTokenChange}
        placeholder="Reset token"
        autoCapitalize="none"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
      />
      <AuthInput
        value={newPassword}
        onChangeText={setNewPassword}
        placeholder="New password"
        secureTextEntry={!showPassword}
        autoComplete="password-new"
        textContentType="newPassword"
      />
      <AuthInput
        value={confirmPassword}
        onChangeText={setConfirmPassword}
        placeholder="Confirm new password"
        secureTextEntry={!showPassword}
        autoComplete="password-new"
        textContentType="newPassword"
      />

      <TouchableOpacity onPress={() => setShowPassword((prev) => !prev)}>
        <Text style={{ color: theme.colors.primary, fontWeight: '600' }}>
          {showPassword ? 'Hide passwords' : 'Show passwords'}
        </Text>
      </TouchableOpacity>

      <AuthError message={error} />
      <AuthSuccess message={success} />
      <ThemedButton label="Reset password" onPress={handleSubmit} loading={submitting} disabled={submitting} />
      <AuthLink label="Back to sign in" onPress={onGoToSignIn} />
    </AuthScreenLayout>
  );
}
