import { Pressable, StyleSheet, Text } from 'react-native';

import { theme } from '../theme';

type ThemedButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
};

export function ThemedButton({ label, onPress, variant = 'primary' }: ThemedButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        variant === 'primary' ? styles.primary : styles.secondary,
        pressed && styles.pressed,
      ]}
    >
      <Text style={[styles.label, variant === 'secondary' && styles.secondaryLabel]}>{label}</Text>
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
});
