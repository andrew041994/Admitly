import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { ThemedCard } from '../../components/ThemedCard';
import { textStyles, theme } from '../../theme';

type WelcomeScreenProps = {
  onGetStarted: () => void;
  onCreateAccount: () => void;
};

export function WelcomeScreen({ onGetStarted, onCreateAccount }: WelcomeScreenProps) {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={styles.brand}>ADMITLY</Text>
        <Text style={textStyles.title}>Where premium nights begin.</Text>
        <Text style={textStyles.body}>
          Discover high-energy events and keep your tickets ready in one polished app experience.
        </Text>

        <ThemedCard>
          <Text style={textStyles.label}>Phase 1 foundation ready</Text>
          <Text style={styles.cardBody}>Navigation, session bootstrap, API config, and dark-gold UI baseline.</Text>
        </ThemedCard>

        <ThemedButton label="Sign In" onPress={onGetStarted} />
        <ThemedButton label="Create Account" onPress={onCreateAccount} variant="secondary" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    gap: theme.spacing.lg,
  },
  brand: {
    color: theme.colors.primary,
    letterSpacing: 3,
    fontWeight: '800',
  },
  cardBody: {
    marginTop: theme.spacing.sm,
    color: theme.colors.textSecondary,
  },
});
