import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

type Props = { title: string; message: string; onDone: () => void };

export function PurchaseResultScreen({ title, message, onDone }: Props) {
  return (
    <Screen>
      <View style={styles.content}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.message}>{message}</Text>
        <ThemedButton label="Done" onPress={onDone} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.spacing.md },
  title: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: theme.typography.heading },
  message: { color: theme.colors.textSecondary },
});
