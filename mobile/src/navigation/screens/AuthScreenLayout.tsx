import { PropsWithChildren } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { Screen } from '../../components/Screen';
import { textStyles, theme } from '../../theme';

type AuthScreenLayoutProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
}>;

export function AuthScreenLayout({ title, subtitle, children }: AuthScreenLayoutProps) {
  return (
    <Screen padded={false}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.flex}>
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.brand}>ADMITLY</Text>
          <Text style={textStyles.heading}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          <View style={styles.form}>{children}</View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

export function AuthInput({
  value,
  onChangeText,
  placeholder,
  secureTextEntry,
  autoCapitalize = 'none',
  keyboardType,
  autoComplete,
  textContentType,
}: {
  value: string;
  onChangeText: (text: string) => void;
  placeholder: string;
  secureTextEntry?: boolean;
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
  keyboardType?: 'default' | 'email-address';
  autoComplete?:
    | 'email'
    | 'name'
    | 'password'
    | 'password-new'
    | 'off'
    | 'username'
    | 'one-time-code';
  textContentType?: 'name' | 'emailAddress' | 'password' | 'newPassword' | 'oneTimeCode' | 'none';
}) {
  return (
    <TextInput
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={theme.colors.textSecondary}
      style={styles.input}
      secureTextEntry={secureTextEntry}
      autoCapitalize={autoCapitalize}
      keyboardType={keyboardType}
      autoCorrect={false}
      autoComplete={autoComplete}
      textContentType={textContentType}
    />
  );
}

export function AuthError({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }

  return <Text style={styles.error}>{message}</Text>;
}

export function AuthSuccess({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }

  return <Text style={styles.success}>{message}</Text>;
}

export function AuthLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress}>
      <Text style={styles.link}>{label}</Text>
    </TouchableOpacity>
  );
}

export const authStyles = StyleSheet.create({
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
});

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.xl,
    gap: theme.spacing.md,
  },
  brand: {
    color: theme.colors.primary,
    letterSpacing: 3,
    fontWeight: '800',
    marginBottom: theme.spacing.sm,
  },
  subtitle: {
    ...textStyles.body,
    marginTop: -theme.spacing.sm,
  },
  form: {
    marginTop: theme.spacing.sm,
    gap: theme.spacing.md,
  },
  input: {
    backgroundColor: theme.colors.surfaceElevated,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    color: theme.colors.textPrimary,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    fontSize: theme.typography.body,
  },
  link: {
    color: theme.colors.primary,
    fontSize: theme.typography.label,
    fontWeight: '600',
  },
  error: {
    color: theme.colors.error,
    fontSize: theme.typography.label,
  },
  success: {
    color: theme.colors.success,
    fontSize: theme.typography.label,
  },
});
