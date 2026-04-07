import { useState } from 'react';
import { Text, TouchableOpacity } from 'react-native';

import { ThemedButton } from '../../components/ThemedButton';
import { getErrorMessage, useSession } from '../../context/SessionContext';
import { theme } from '../../theme';
import { AuthError, AuthInput, AuthLink, AuthScreenLayout } from './AuthScreenLayout';

type SignInScreenProps = {
  onGoToSignUp: () => void;
  onGoToForgotPassword: () => void;
};

export function SignInScreen({ onGoToSignUp, onGoToForgotPassword }: SignInScreenProps) {
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submitDisabled = submitting;

  async function handleSignIn() {
    if (!email.trim() || !password) {
      setError('Please enter both email and password.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await signIn(email, password);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScreenLayout title="Sign In" subtitle="Welcome back. Access your premium event experience.">
      <AuthInput
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        keyboardType="email-address"
        autoComplete="email"
        textContentType="emailAddress"
      />

      <AuthInput
        value={password}
        onChangeText={setPassword}
        placeholder="Password"
        secureTextEntry={!showPassword}
        autoComplete="password"
        textContentType="password"
      />

      <TouchableOpacity onPress={() => setShowPassword((prev) => !prev)}>
        <Text style={{ color: theme.colors.primary, fontWeight: '600' }}>
          {showPassword ? 'Hide password' : 'Show password'}
        </Text>
      </TouchableOpacity>

      <AuthError message={error} />

      <ThemedButton label="Sign In" onPress={handleSignIn} loading={submitting} disabled={submitDisabled} />

      <AuthLink label="Forgot password?" onPress={onGoToForgotPassword} />
      <AuthLink label="New to Admitly? Create account" onPress={onGoToSignUp} />
    </AuthScreenLayout>
  );
}
