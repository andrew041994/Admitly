import { StyleSheet, Text, View } from 'react-native';

import { Screen } from '../../components/Screen';
import { textStyles, theme } from '../../theme';

type PlaceholderScreenProps = {
  title: string;
  description: string;
};

export function PlaceholderScreen({ title, description }: PlaceholderScreenProps) {
  return (
    <Screen>
      <View style={styles.container}>
        <Text style={textStyles.heading}>{title}</Text>
        <Text style={textStyles.body}>{description}</Text>
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
