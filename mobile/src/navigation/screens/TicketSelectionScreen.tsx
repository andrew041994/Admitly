import { useMemo, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { EventDiscoveryDetail } from '../../api/events';
import { createOrderFromSelection } from '../../api/orders';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

type Props = {
  event: EventDiscoveryDetail;
  onOrderCreated: (orderId: number) => void;
};

export function TicketSelectionScreen({ event, onOrderCreated }: Props) {
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [submitting, setSubmitting] = useState(false);

  const rows = event.ticket_tiers.filter((tier) => tier.is_active && tier.available_quantity > 0);

  const subtotal = useMemo(
    () => rows.reduce((sum, tier) => sum + (quantities[tier.id] ?? 0) * Number(tier.price_amount), 0),
    [quantities, rows],
  );

  const selectedItems = rows
    .map((tier) => ({ ticket_tier_id: tier.id, quantity: quantities[tier.id] ?? 0 }))
    .filter((item) => item.quantity > 0);

  async function handleContinue() {
    if (!selectedItems.length) {
      Alert.alert('Select tickets', 'Choose at least one ticket before continuing.');
      return;
    }

    setSubmitting(true);
    try {
      const order = await createOrderFromSelection(event.id, selectedItems);
      onOrderCreated(order.id);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not create order.';
      Alert.alert('Purchase unavailable', message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Select tickets</Text>
        {rows.map((tier) => {
          const quantity = quantities[tier.id] ?? 0;
          return (
            <View key={tier.id} style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{tier.name}</Text>
                <Text style={styles.meta}>{tier.currency} {tier.price_amount}</Text>
                <Text style={styles.meta}>{tier.available_quantity} left</Text>
              </View>
              <View style={styles.counter}>
                <ThemedButton label="-" variant="secondary" onPress={() => setQuantities((q) => ({ ...q, [tier.id]: Math.max(0, quantity - 1) }))} />
                <Text style={styles.qty}>{quantity}</Text>
                <ThemedButton label="+" variant="secondary" onPress={() => setQuantities((q) => ({ ...q, [tier.id]: Math.min(tier.max_per_order, quantity + 1) }))} />
              </View>
            </View>
          );
        })}

        <View style={styles.summary}>
          <Text style={styles.meta}>Subtotal</Text>
          <Text style={styles.total}>{event.price_summary?.currency ?? 'GYD'} {subtotal.toFixed(2)}</Text>
        </View>
        <ThemedButton label={submitting ? 'Creating order...' : 'Continue'} onPress={handleContinue} disabled={submitting} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: theme.spacing.md, paddingBottom: theme.spacing.xl },
  title: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: theme.typography.heading },
  row: { borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, padding: theme.spacing.md, flexDirection: 'row', gap: theme.spacing.sm },
  name: { color: theme.colors.textPrimary, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary },
  counter: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm },
  qty: { color: theme.colors.textPrimary, minWidth: 24, textAlign: 'center' },
  summary: { padding: theme.spacing.md, borderRadius: theme.radius.md, backgroundColor: theme.colors.surface },
  total: { color: theme.colors.primary, fontWeight: '700' },
});
