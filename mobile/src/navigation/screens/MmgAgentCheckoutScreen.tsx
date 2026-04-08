import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { completeMmgAgentPayment } from '../../api/orders';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

type Props = {
  orderId: number;
  referenceCode: string;
  onResult: (title: string, message: string) => void;
};

export function MmgAgentCheckoutScreen({ orderId, referenceCode, onResult }: Props) {
  const [status, setStatus] = useState('Awaiting payment at MMG agent.');
  const [loading, setLoading] = useState(false);

  async function completePayment() {
    setLoading(true);
    try {
      const res = await completeMmgAgentPayment(orderId, referenceCode);
      if (res.payment_verification_status === 'verified') {
        onResult('Purchase successful', 'Payment verified and tickets confirmed.');
        return;
      }
      setStatus(res.message);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to verify payment yet.';
      setStatus(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen>
      <View style={styles.content}>
        <Text style={styles.title}>Pay at MMG agent</Text>
        <Text style={styles.code}>{referenceCode}</Text>
        <Text style={styles.meta}>Give this reference code to the MMG agent. Tickets activate only after verification.</Text>
        <Text style={styles.meta}>{status}</Text>
        <ThemedButton label={loading ? 'Checking...' : 'Complete Payment'} onPress={completePayment} disabled={loading} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.spacing.md },
  title: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: theme.typography.heading },
  code: { color: theme.colors.primary, fontWeight: '700', fontSize: 24 },
  meta: { color: theme.colors.textSecondary },
});
