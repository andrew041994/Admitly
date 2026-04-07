import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { textStyles, theme } from '../../theme';

type SignInScreenProps = {
  onContinue: () => void;
};

export function SignInScreen({ onContinue }: SignInScreenProps) {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={textStyles.heading}>Sign In</Text>
        <Text style={textStyles.body}>Authentication wiring arrives in Phase 2. Continue with placeholder session.</Text>
        <ThemedButton label="Continue (Placeholder)" onPress={onContinue} />
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
});
