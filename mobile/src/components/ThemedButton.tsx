import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { theme } from '../theme';

type ThemedButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  loading?: boolean;
};

export function ThemedButton({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
}: ThemedButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.base,
        variant === 'primary' ? styles.primary : styles.secondary,
        (pressed || disabled || loading) && styles.pressed,
      ]}
    >
      <View style={styles.content}>
        {loading ? <ActivityIndicator color={variant === 'primary' ? '#090909' : theme.colors.primary} /> : null}
        <Text style={[styles.label, variant === 'secondary' && styles.secondaryLabel]}>{label}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.md,
  },
  primary: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  secondary: {
    backgroundColor: 'transparent',
    borderColor: theme.colors.primaryMuted,
  },
  pressed: {
    opacity: 0.85,
  },
  label: {
    color: '#090909',
    fontWeight: '700',
    fontSize: theme.typography.label,
  },
  secondaryLabel: {
    color: theme.colors.primary,
  },
  content: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
    alignItems: 'center',
  },
});
