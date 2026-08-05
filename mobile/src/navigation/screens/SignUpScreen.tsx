import { useState } from 'react';
import { Text, TouchableOpacity } from 'react-native';

import { ThemedButton } from '../../components/ThemedButton';
import { getErrorMessage, useSession } from '../../context/SessionContext';
import { theme } from '../../theme';
import { AuthError, AuthInput, AuthLink, AuthScreenLayout } from './AuthScreenLayout';
import { normalizePhoneNumber } from '../../features/transfers/validation';

type SignUpScreenProps = {
  onGoToSignIn: () => void;
};

export function SignUpScreen({ onGoToSignIn }: SignUpScreenProps) {
  const { signUp } = useSession();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSignUp() {
    if (!fullName.trim() || !email.trim() || !phoneNumber.trim() || !password || !confirmPassword) {
      setError('Please complete all fields.');
      return;
    }

    const normalizedPhone = normalizePhoneNumber(phoneNumber);
    if (!normalizedPhone) {
      setError('Enter a valid Guyana number or an international number with country code.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await signUp(fullName, email, normalizedPhone, password);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScreenLayout title="Create Account" subtitle="Join Admitly and keep your nights organized.">
      <AuthInput
        value={fullName}
        onChangeText={setFullName}
        placeholder="Full name"
        autoCapitalize="words"
        autoComplete="name"
        textContentType="name"
      />
      <AuthInput
        value={phoneNumber}
        onChangeText={setPhoneNumber}
        placeholder="Phone number"
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
      />
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
        autoComplete="password-new"
        textContentType="newPassword"
      />
      <AuthInput
        value={confirmPassword}
        onChangeText={setConfirmPassword}
        placeholder="Confirm password"
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

      <ThemedButton label="Create Account" onPress={handleSignUp} loading={submitting} disabled={submitting} />

      <AuthLink label="Already have an account? Sign in" onPress={onGoToSignIn} />
    </AuthScreenLayout>
  );
}
