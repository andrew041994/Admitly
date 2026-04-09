import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../api/client';
import { createEvent } from '../../api/organizer';
import { theme } from '../../theme';

type TierFormState = {
  name: string;
  description: string;
  priceAmount: string;
  currency: string;
  quantityTotal: string;
  minPerOrder: string;
  maxPerOrder: string;
};

const defaultTier = (): TierFormState => ({
  name: '',
  description: '',
  priceAmount: '0.00',
  currency: 'GYD',
  quantityTotal: '100',
  minPerOrder: '1',
  maxPerOrder: '10',
});

export function CreateEventScreen({ onCreated }: { onCreated: (eventId: number) => void }) {
  const [title, setTitle] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [longDescription, setLongDescription] = useState('');
  const [category, setCategory] = useState('');
  const [startAt, setStartAt] = useState('');
  const [endAt, setEndAt] = useState('');
  const [doorsOpenAt, setDoorsOpenAt] = useState('');
  const [salesStartAt, setSalesStartAt] = useState('');
  const [salesEndAt, setSalesEndAt] = useState('');
  const [timezone, setTimezone] = useState('America/Guyana');
  const [venueName, setVenueName] = useState('');
  const [addressText, setAddressText] = useState('');
  const [refundPolicyText, setRefundPolicyText] = useState('');
  const [termsText, setTermsText] = useState('');
  const [tiers, setTiers] = useState<TierFormState[]>([defaultTier()]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canRemoveTier = tiers.length > 1;

  const addTier = () => setTiers((current) => [...current, defaultTier()]);
  const removeTier = (index: number) => {
    if (tiers.length === 1) return;
    setTiers((current) => current.filter((_, idx) => idx !== index));
  };

  const updateTier = (index: number, patch: Partial<TierFormState>) => {
    setTiers((current) => current.map((tier, idx) => (idx === index ? { ...tier, ...patch } : tier)));
  };

  const submitValidationError = useMemo(() => {
    if (!title.trim()) return 'Event title is required.';
    if (!startAt.trim() || !endAt.trim()) return 'Start and end date/time are required.';
    if (!venueName.trim()) return 'Venue name is required for MVP event creation.';
    if (tiers.length < 1) return 'At least one ticket tier is required.';

    for (let i = 0; i < tiers.length; i += 1) {
      const tier = tiers[i];
      if (!tier.name.trim()) return `Tier ${i + 1}: name is required.`;
      const price = Number(tier.priceAmount);
      const quantity = Number(tier.quantityTotal);
      const minPerOrder = Number(tier.minPerOrder);
      const maxPerOrder = Number(tier.maxPerOrder);
      if (Number.isNaN(price) || price < 0) return `Tier ${i + 1}: price must be zero or greater.`;
      if (!Number.isInteger(quantity) || quantity <= 0) return `Tier ${i + 1}: quantity must be a positive integer.`;
      if (!Number.isInteger(minPerOrder) || minPerOrder < 1) return `Tier ${i + 1}: minimum per order must be at least 1.`;
      if (!Number.isInteger(maxPerOrder) || maxPerOrder < minPerOrder) return `Tier ${i + 1}: maximum per order must be greater than or equal to minimum.`;
      if (!tier.currency.trim() || tier.currency.trim().length !== 3) return `Tier ${i + 1}: currency must be a 3-letter code.`;
    }

    return null;
  }, [title, startAt, endAt, venueName, tiers]);

  const submit = async () => {
    if (submitValidationError) {
      setError(submitValidationError);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const created = await createEvent({
        title: title.trim(),
        short_description: shortDescription.trim() || null,
        long_description: longDescription.trim() || null,
        category: category.trim() || null,
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
        doors_open_at: doorsOpenAt.trim() ? new Date(doorsOpenAt).toISOString() : null,
        sales_start_at: salesStartAt.trim() ? new Date(salesStartAt).toISOString() : null,
        sales_end_at: salesEndAt.trim() ? new Date(salesEndAt).toISOString() : null,
        timezone: timezone.trim() || 'America/Guyana',
        custom_venue_name: venueName.trim(),
        custom_address_text: addressText.trim() || null,
        refund_policy_text: refundPolicyText.trim() || null,
        terms_text: termsText.trim() || null,
        ticket_tiers: tiers.map((tier, index) => ({
          name: tier.name.trim(),
          description: tier.description.trim() || null,
          price_amount: Number(tier.priceAmount).toFixed(2),
          currency: tier.currency.trim().toUpperCase(),
          quantity_total: Number(tier.quantityTotal),
          min_per_order: Number(tier.minPerOrder),
          max_per_order: Number(tier.maxPerOrder),
          sort_order: index,
        })),
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to create event.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Create Event</Text>

      <Text style={styles.sectionTitle}>Basic Info</Text>
      <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="Event title" placeholderTextColor={theme.colors.textSecondary} />
      <TextInput style={styles.input} value={shortDescription} onChangeText={setShortDescription} placeholder="Short description" placeholderTextColor={theme.colors.textSecondary} />
      <TextInput
        style={[styles.input, styles.multiline]}
        multiline
        numberOfLines={4}
        value={longDescription}
        onChangeText={setLongDescription}
        placeholder="Long description"
        placeholderTextColor={theme.colors.textSecondary}
      />
      <TextInput style={styles.input} value={category} onChangeText={setCategory} placeholder="Category" placeholderTextColor={theme.colors.textSecondary} />

      <Text style={styles.sectionTitle}>Timing (ISO format)</Text>
      <TextInput style={styles.input} value={startAt} onChangeText={setStartAt} placeholder="Start (e.g. 2026-06-12T18:00:00-04:00)" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />
      <TextInput style={styles.input} value={endAt} onChangeText={setEndAt} placeholder="End (e.g. 2026-06-12T22:00:00-04:00)" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />
      <TextInput style={styles.input} value={doorsOpenAt} onChangeText={setDoorsOpenAt} placeholder="Doors open at (optional ISO)" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />
      <TextInput style={styles.input} value={salesStartAt} onChangeText={setSalesStartAt} placeholder="Sales start at (optional ISO)" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />
      <TextInput style={styles.input} value={salesEndAt} onChangeText={setSalesEndAt} placeholder="Sales end at (optional ISO)" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />
      <TextInput style={styles.input} value={timezone} onChangeText={setTimezone} placeholder="Timezone" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="none" />

      <Text style={styles.sectionTitle}>Venue / Location</Text>
      <TextInput style={styles.input} value={venueName} onChangeText={setVenueName} placeholder="Venue name" placeholderTextColor={theme.colors.textSecondary} />
      <TextInput
        style={[styles.input, styles.multiline]}
        multiline
        numberOfLines={3}
        value={addressText}
        onChangeText={setAddressText}
        placeholder="Address"
        placeholderTextColor={theme.colors.textSecondary}
      />

      <Text style={styles.sectionTitle}>Ticket Tiers</Text>
      {tiers.map((tier, index) => (
        <View key={`tier-${index}`} style={styles.tierCard}>
          <Text style={styles.tierTitle}>Tier {index + 1}</Text>
          <TextInput style={styles.input} value={tier.name} onChangeText={(value) => updateTier(index, { name: value })} placeholder="Tier name" placeholderTextColor={theme.colors.textSecondary} />
          <TextInput style={styles.input} value={tier.description} onChangeText={(value) => updateTier(index, { description: value })} placeholder="Description" placeholderTextColor={theme.colors.textSecondary} />
          <View style={styles.row}>
            <TextInput style={[styles.input, styles.half]} value={tier.priceAmount} onChangeText={(value) => updateTier(index, { priceAmount: value })} placeholder="Price" placeholderTextColor={theme.colors.textSecondary} keyboardType="decimal-pad" />
            <TextInput style={[styles.input, styles.half]} value={tier.currency} onChangeText={(value) => updateTier(index, { currency: value })} placeholder="Currency" placeholderTextColor={theme.colors.textSecondary} autoCapitalize="characters" />
          </View>
          <View style={styles.row}>
            <TextInput style={[styles.input, styles.half]} value={tier.quantityTotal} onChangeText={(value) => updateTier(index, { quantityTotal: value })} placeholder="Quantity" placeholderTextColor={theme.colors.textSecondary} keyboardType="number-pad" />
            <TextInput style={[styles.input, styles.half]} value={tier.minPerOrder} onChangeText={(value) => updateTier(index, { minPerOrder: value })} placeholder="Min/order" placeholderTextColor={theme.colors.textSecondary} keyboardType="number-pad" />
          </View>
          <TextInput style={styles.input} value={tier.maxPerOrder} onChangeText={(value) => updateTier(index, { maxPerOrder: value })} placeholder="Max/order" placeholderTextColor={theme.colors.textSecondary} keyboardType="number-pad" />
          {canRemoveTier ? (
            <Pressable onPress={() => removeTier(index)} style={styles.removeButton}>
              <Text style={styles.removeButtonText}>Remove Tier</Text>
            </Pressable>
          ) : null}
        </View>
      ))}
      <Pressable onPress={addTier} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Add Tier</Text>
      </Pressable>

      <Text style={styles.sectionTitle}>Policies</Text>
      <TextInput
        style={[styles.input, styles.multiline]}
        multiline
        numberOfLines={3}
        value={refundPolicyText}
        onChangeText={setRefundPolicyText}
        placeholder="Refund policy"
        placeholderTextColor={theme.colors.textSecondary}
      />
      <TextInput
        style={[styles.input, styles.multiline]}
        multiline
        numberOfLines={3}
        value={termsText}
        onChangeText={setTermsText}
        placeholder="Terms"
        placeholderTextColor={theme.colors.textSecondary}
      />

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable onPress={submit} style={[styles.button, loading ? styles.buttonDisabled : null]} disabled={loading}>
        <Text style={styles.buttonText}>{loading ? 'Creating…' : 'Create Event'}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: theme.spacing.lg, backgroundColor: theme.colors.background, gap: theme.spacing.sm },
  title: { color: theme.colors.textPrimary, fontSize: 24, fontWeight: '700' },
  sectionTitle: { color: theme.colors.primary, fontSize: 16, fontWeight: '700', marginTop: theme.spacing.md },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    color: theme.colors.textPrimary,
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surface,
  },
  multiline: { minHeight: 90, textAlignVertical: 'top' },
  row: { flexDirection: 'row', gap: theme.spacing.sm },
  half: { flex: 1 },
  tierCard: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    backgroundColor: theme.colors.surfaceElevated,
    gap: theme.spacing.sm,
  },
  tierTitle: { color: theme.colors.textPrimary, fontWeight: '700' },
  secondaryButton: {
    borderWidth: 1,
    borderColor: theme.colors.primary,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    alignItems: 'center',
  },
  secondaryButtonText: { color: theme.colors.primary, fontWeight: '700' },
  removeButton: {
    borderWidth: 1,
    borderColor: theme.colors.error,
    borderRadius: theme.radius.sm,
    padding: theme.spacing.sm,
    alignItems: 'center',
  },
  removeButtonText: { color: theme.colors.error, fontWeight: '600' },
  button: { backgroundColor: theme.colors.primary, borderRadius: theme.radius.md, padding: theme.spacing.md, marginTop: theme.spacing.sm },
  buttonDisabled: { opacity: 0.7 },
  buttonText: { color: '#111', fontWeight: '700', textAlign: 'center' },
  error: { color: theme.colors.error },
});
