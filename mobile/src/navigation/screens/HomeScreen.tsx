import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { ThemedCard } from '../../components/ThemedCard';
import { textStyles, theme } from '../../theme';

type HomeScreenProps = {
  onOpenProfile: () => void;
  onSignOut: () => void;
};

export function HomeScreen({ onOpenProfile, onSignOut }: HomeScreenProps) {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={styles.kicker}>ADMITLY MEMBER</Text>
        <Text style={textStyles.heading}>Home shell</Text>
        <ThemedCard>
          <Text style={textStyles.label}>Next phases route here</Text>
          <Text style={styles.body}>Event discovery, checkout, wallet, and scanning are intentionally not implemented yet.</Text>
        </ThemedCard>

        <ThemedButton label="Profile Placeholder" onPress={onOpenProfile} variant="secondary" />
        <ThemedButton label="Sign Out" onPress={onSignOut} variant="secondary" />
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
  kicker: {
    color: theme.colors.primary,
    fontSize: theme.typography.caption,
    letterSpacing: 2,
  },
  body: {
    marginTop: theme.spacing.sm,
    color: theme.colors.textSecondary,
  },
});
