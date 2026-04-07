import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { textStyles, theme } from '../../theme';

export function SignUpScreen() {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={textStyles.heading}>Create account</Text>
        <Text style={textStyles.body}>Sign up flow scaffold only. Full onboarding arrives in a later phase.</Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    gap: theme.spacing.md,
  },
});
