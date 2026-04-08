import { Alert, StyleSheet, Text, View } from 'react-native';
import * as Linking from 'expo-linking';

import { ApiError } from '../../api/client';
import { getOrder, initiateMmgAgentCheckout, initiateMmgCheckout } from '../../api/orders';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';
import { useState } from 'react';

type Props = {
  orderId: number;
  onOpenAgent: (referenceCode: string) => void;
  onResult: (title: string, message: string) => void;
};

export function CheckoutMethodScreen({ orderId, onOpenAgent, onResult }: Props) {
  const [loading, setLoading] = useState(false);

  async function handleMmg() {
    setLoading(true);
    try {
      const checkout = await initiateMmgCheckout(orderId);
      if (checkout.checkout_url) {
        await Linking.openURL(checkout.checkout_url);
      }
      const order = await getOrder(orderId);
      onResult('Payment initiated', `Reference: ${order.reference_code}. Complete payment to confirm tickets.`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to initiate MMG checkout.';
      Alert.alert('Checkout error', message);
    } finally {
      setLoading(false);
    }
  }

  async function handleAgent() {
    setLoading(true);
    try {
      const initiated = await initiateMmgAgentCheckout(orderId);
      onOpenAgent(initiated.payment_reference);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to start MMG agent flow.';
      Alert.alert('Checkout error', message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen>
      <View style={styles.content}>
        <Text style={styles.title}>Choose payment method</Text>
        <Text style={styles.meta}>Every order has a reference code for support and reconciliation.</Text>
        <ThemedButton label={loading ? 'Please wait...' : 'MMG Checkout'} onPress={handleMmg} disabled={loading} />
        <ThemedButton label={loading ? 'Please wait...' : 'MMG Agent Checkout'} variant="secondary" onPress={handleAgent} disabled={loading} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.spacing.md },
  title: { color: theme.colors.textPrimary, fontSize: theme.typography.heading, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary },
});
