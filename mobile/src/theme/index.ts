import { StyleSheet } from 'react-native';

import { colors, radius, spacing, typography } from './tokens';

export const theme = {
  colors,
  spacing,
  radius,
  typography,
};

export const textStyles = StyleSheet.create({
  title: {
    color: colors.textPrimary,
    fontSize: typography.title,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  heading: {
    color: colors.textPrimary,
    fontSize: typography.heading,
    fontWeight: '600',
  },
  body: {
    color: colors.textSecondary,
    fontSize: typography.body,
    lineHeight: 24,
  },
  label: {
    color: colors.textPrimary,
    fontSize: typography.label,
    fontWeight: '600',
  },
});
