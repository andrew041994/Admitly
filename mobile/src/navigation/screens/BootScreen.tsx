import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { textStyles, theme } from '../../theme';

export function BootScreen() {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={textStyles.title}>ADMITLY</Text>
        <Text style={styles.tagline}>Premium nights. Seamless entry.</Text>
        <ActivityIndicator color={theme.colors.primary} size="large" style={styles.loader} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: theme.spacing.md,
  },
  tagline: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.label,
  },
  loader: {
    marginTop: theme.spacing.lg,
  },
});
