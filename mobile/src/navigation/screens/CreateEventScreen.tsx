import { useEffect, useMemo, useState } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';

import { ApiError } from '../../api/client';
import { createEvent, searchVenues, VenueSearchItem } from '../../api/organizer';
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
  quantityTotal: '',
  minPerOrder: '',
  maxPerOrder: '',
});

const GUYANA_TIMEZONE = 'America/Guyana';
const CATEGORY_OPTIONS = [
  'Party',
  'Concert',
  'Festival',
  'Cricket',
  'Football',
  'Soccer',
  'Basketball',
  'Bar-B-Que',
  'Car Show',
  'Car & Bike Show',
  'Car Audio Show',
  'Conference',
  'Workshop',
  'Seminar',
  'Networking',
  'Sports',
  'Fitness',
  'Food & Drink',
  'Brunch',
  'Nightlife',
  'Comedy',
  'Exhibition',
  'Art',
  'Culture',
  'Family',
  'Kids',
  'Community',
  'Fundraiser',
  'Religious',
  'Business',
  'Fashion',
  'Beauty',
  'Wellness',
  'Travel',
  'Holiday',
  'Education',
  'Tech',
  'Other',
] as const;

type DateTimeField = {
  date: Date | null;
  time: Date | null;
};

type DateTimeFieldKey = 'start_at' | 'end_at' | 'sales_start_at' | 'sales_end_at';

type PickerField =
  | 'start_date'
  | 'start_time'
  | 'end_date'
  | 'end_time'
  | 'doors_open_time'
  | 'sales_start_date'
  | 'sales_start_time'
  | 'sales_end_date'
  | 'sales_end_time';

type PickerSession = {
  field: PickerField;
  mode: 'date' | 'time';
  value: Date;
  selectedDate?: Date;
} | null;

const formatDate = (value: Date) =>
  new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(value);

const formatTime = (value: Date) => new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(value);

const formatDateTimeValue = (field: DateTimeField) => {
  if (!field.date || !field.time) return 'Select date and time';
  return `${formatDate(field.date)} • ${formatTime(field.time)}`;
};

const getPickerTitle = (field: PickerField) => {
  if (field.startsWith('start_')) return 'Event start';
  if (field.startsWith('end_')) return 'Event end';
  if (field === 'doors_open_time') return 'Doors open';
  if (field.startsWith('sales_start_')) return 'Sales start';
  return 'Sales end';
};

const getPickerStepLabel = (session: Exclude<PickerSession, null>) => {
  if (session.field === 'doors_open_time') return 'Select time';
  return session.mode === 'date' ? 'Step 1 of 2 • Select date' : 'Step 2 of 2 • Select time';
};

const buildGuyanaIso = (date: Date, time: Date) => {
  const year = date.getFullYear();
  const month = date.getMonth();
  const day = date.getDate();
  const hour = time.getHours();
  const minute = time.getMinutes();
  const utcMillis = Date.UTC(year, month, day, hour + 4, minute, 0, 0);
  return new Date(utcMillis).toISOString();
};

export function CreateEventScreen({ onCreated }: { onCreated: (eventId: number) => void }) {
  const [title, setTitle] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [longDescription, setLongDescription] = useState('');
  const [category, setCategory] = useState('');
  const [isCategoryPickerVisible, setIsCategoryPickerVisible] = useState(false);
  const [categorySearch, setCategorySearch] = useState('');
  const [startAt, setStartAt] = useState<DateTimeField>({ date: null, time: null });
  const [endAt, setEndAt] = useState<DateTimeField>({ date: null, time: null });
  const [doorsOpenAt, setDoorsOpenAt] = useState<Date | null>(null);
  const [salesStartAt, setSalesStartAt] = useState<DateTimeField>({ date: null, time: null });
  const [salesEndAt, setSalesEndAt] = useState<DateTimeField>({ date: null, time: null });
  const [pickerSession, setPickerSession] = useState<PickerSession>(null);
  const [pickerDraftValue, setPickerDraftValue] = useState<Date>(new Date());
  const [venueName, setVenueName] = useState('');
  const [addressText, setAddressText] = useState('');
  const [selectedVenueId, setSelectedVenueId] = useState<number | null>(null);
  const [venueSuggestions, setVenueSuggestions] = useState<VenueSearchItem[]>([]);
  const [loadingVenueSuggestions, setLoadingVenueSuggestions] = useState(false);
  const [refundPolicyText, setRefundPolicyText] = useState('');
  const [termsText, setTermsText] = useState('');
  const [tiers, setTiers] = useState<TierFormState[]>([defaultTier()]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalizedCategoryOptions = useMemo(() => {
    const seen = new Set<string>();
    return CATEGORY_OPTIONS.filter((option) => {
      const normalized = option.trim().toLowerCase();
      if (seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    });
  }, []);

  const trimmedCategorySearch = categorySearch.trim();
  const filteredCategoryOptions = useMemo(() => {
    if (!trimmedCategorySearch) return normalizedCategoryOptions;
    const normalizedSearch = trimmedCategorySearch.toLowerCase();
    return normalizedCategoryOptions.filter((option) => option.toLowerCase().includes(normalizedSearch));
  }, [normalizedCategoryOptions, trimmedCategorySearch]);

  const exactMatchedCategoryOption = useMemo(() => {
    if (!trimmedCategorySearch) return null;
    const normalizedSearch = trimmedCategorySearch.toLowerCase();
    return normalizedCategoryOptions.find((option) => option.toLowerCase() === normalizedSearch) ?? null;
  }, [normalizedCategoryOptions, trimmedCategorySearch]);

  const canRemoveTier = tiers.length > 1;
  const trimmedVenueName = venueName.trim();

  useEffect(() => {
    let isCancelled = false;
    if (!trimmedVenueName || trimmedVenueName.length < 2) {
      setVenueSuggestions([]);
      setLoadingVenueSuggestions(false);
      return () => {
        isCancelled = true;
      };
    }
    const timeout = setTimeout(async () => {
      setLoadingVenueSuggestions(true);
      try {
        const results = await searchVenues(trimmedVenueName, 8);
        if (!isCancelled) {
          setVenueSuggestions(results);
        }
      } catch {
        if (!isCancelled) {
          setVenueSuggestions([]);
        }
      } finally {
        if (!isCancelled) {
          setLoadingVenueSuggestions(false);
        }
      }
    }, 250);

    return () => {
      isCancelled = true;
      clearTimeout(timeout);
    };
  }, [trimmedVenueName]);

  const onChangeVenueName = (value: string) => {
    setVenueName(value);
    if (selectedVenueId !== null) {
      const selected = venueSuggestions.find((venue) => venue.id === selectedVenueId);
      if (!selected || selected.name.trim().toLowerCase() !== value.trim().toLowerCase()) {
        setSelectedVenueId(null);
      }
    }
  };

  const onChangeAddressText = (value: string) => {
    setAddressText(value);
    if (selectedVenueId !== null) {
      const selected = venueSuggestions.find((venue) => venue.id === selectedVenueId);
      if (!selected || (selected.address_text ?? '').trim() !== value.trim()) {
        setSelectedVenueId(null);
      }
    }
  };

  const selectVenueSuggestion = (venue: VenueSearchItem) => {
    setSelectedVenueId(venue.id);
    setVenueName(venue.name);
    setAddressText(venue.address_text ?? '');
    setVenueSuggestions([]);
  };

  const addTier = () => setTiers((current) => [...current, defaultTier()]);
  const removeTier = (index: number) => {
    if (tiers.length === 1) return;
    setTiers((current) => current.filter((_, idx) => idx !== index));
  };

  const updateTier = (index: number, patch: Partial<TierFormState>) => {
    setTiers((current) => current.map((tier, idx) => (idx === index ? { ...tier, ...patch } : tier)));
  };

  const openCategoryPicker = () => {
    setCategorySearch(category.trim());
    setIsCategoryPickerVisible(true);
  };

  const closeCategoryPicker = () => {
    setIsCategoryPickerVisible(false);
  };

  const selectCategory = (value: string) => {
    setCategory(value.trim());
    closeCategoryPicker();
  };

  const openPicker = (nextSession: Exclude<PickerSession, null>) => {
    setPickerDraftValue(nextSession.value);
    setPickerSession(nextSession);
  };

  const startDateTimeFlow = (field: DateTimeFieldKey) => {
    const now = new Date();
    if (field === 'start_at') {
      openPicker({ field: 'start_date', mode: 'date', value: startAt.date ?? now });
      return;
    }
    if (field === 'end_at') {
      openPicker({ field: 'end_date', mode: 'date', value: endAt.date ?? startAt.date ?? now });
      return;
    }
    if (field === 'sales_start_at') {
      openPicker({ field: 'sales_start_date', mode: 'date', value: salesStartAt.date ?? now });
      return;
    }
    openPicker({ field: 'sales_end_date', mode: 'date', value: salesEndAt.date ?? now });
  };

  const cancelPickerSelection = () => {
    setPickerSession(null);
  };

  const completePickerSelection = () => {
    if (!pickerSession) return;

    if (pickerSession.field === 'doors_open_time') {
      setDoorsOpenAt(pickerDraftValue);
      setPickerSession(null);
      return;
    }

    if (pickerSession.mode === 'date') {
      const nextTimeValue =
        pickerSession.field === 'start_date'
          ? startAt.time ?? pickerDraftValue
          : pickerSession.field === 'end_date'
            ? endAt.time ?? startAt.time ?? pickerDraftValue
            : pickerSession.field === 'sales_start_date'
              ? salesStartAt.time ?? pickerDraftValue
              : salesEndAt.time ?? pickerDraftValue;

      const nextField: PickerField =
        pickerSession.field === 'start_date'
          ? 'start_time'
          : pickerSession.field === 'end_date'
            ? 'end_time'
            : pickerSession.field === 'sales_start_date'
              ? 'sales_start_time'
              : 'sales_end_time';

      setPickerSession({
        field: nextField,
        mode: 'time',
        value: nextTimeValue,
        selectedDate: pickerDraftValue,
      });
      setPickerDraftValue(nextTimeValue);
      return;
    }

    const finalDate = pickerSession.selectedDate;
    if (!finalDate) {
      setPickerSession(null);
      return;
    }

    if (pickerSession.field === 'start_time') {
      setStartAt({ date: finalDate, time: pickerDraftValue });
    } else if (pickerSession.field === 'end_time') {
      setEndAt({ date: finalDate, time: pickerDraftValue });
    } else if (pickerSession.field === 'sales_start_time') {
      setSalesStartAt({ date: finalDate, time: pickerDraftValue });
    } else if (pickerSession.field === 'sales_end_time') {
      setSalesEndAt({ date: finalDate, time: pickerDraftValue });
    }

    setPickerSession(null);
  };

  const submitValidationError = useMemo(() => {
    if (!title.trim()) return 'Event title is required.';
    if (!startAt.date || !startAt.time || !endAt.date || !endAt.time) return 'Start and end date/time are required.';
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
      const startAtIso = buildGuyanaIso(startAt.date as Date, startAt.time as Date);
      const endAtIso = buildGuyanaIso(endAt.date as Date, endAt.time as Date);
      const salesStartAtIso = salesStartAt.date && salesStartAt.time ? buildGuyanaIso(salesStartAt.date, salesStartAt.time) : null;
      const salesEndAtIso = salesEndAt.date && salesEndAt.time ? buildGuyanaIso(salesEndAt.date, salesEndAt.time) : null;
      const doorsOpenAtIso = doorsOpenAt && startAt.date ? buildGuyanaIso(startAt.date, doorsOpenAt) : null;

      const created = await createEvent({
        title: title.trim(),
        short_description: shortDescription.trim() || null,
        long_description: longDescription.trim() || null,
        category: category.trim() || null,
        start_at: startAtIso,
        end_at: endAtIso,
        doors_open_at: doorsOpenAtIso,
        sales_start_at: salesStartAtIso,
        sales_end_at: salesEndAtIso,
        timezone: GUYANA_TIMEZONE,
        venue_id: selectedVenueId,
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
    <>
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
        <Pressable style={styles.input} onPress={openCategoryPicker}>
          <Text style={category.trim() ? styles.pickerValue : styles.placeholderValue}>{category.trim() || 'Category'}</Text>
        </Pressable>

        <Text style={styles.sectionTitle}>Timing</Text>
        <View style={styles.timingCard}>
          <Text style={styles.timingLabel}>Start</Text>
          <Pressable style={styles.input} onPress={() => startDateTimeFlow('start_at')}>
            <Text style={styles.pickerValue}>{formatDateTimeValue(startAt)}</Text>
          </Pressable>
        </View>

        <View style={styles.timingCard}>
          <Text style={styles.timingLabel}>End</Text>
          <Pressable style={styles.input} onPress={() => startDateTimeFlow('end_at')}>
            <Text style={styles.pickerValue}>{formatDateTimeValue(endAt)}</Text>
          </Pressable>
        </View>

        <View style={styles.timingCard}>
          <Text style={styles.timingLabel}>Doors open (optional)</Text>
          <Pressable style={styles.input} onPress={() => openPicker({ field: 'doors_open_time', mode: 'time', value: doorsOpenAt ?? startAt.time ?? new Date() })}>
            <Text style={styles.pickerValue}>{doorsOpenAt ? formatTime(doorsOpenAt) : 'Pick time'}</Text>
          </Pressable>
        </View>

        <View style={styles.timingCard}>
          <Text style={styles.timingLabel}>Sales start (optional)</Text>
          <Pressable style={styles.input} onPress={() => startDateTimeFlow('sales_start_at')}>
            <Text style={styles.pickerValue}>{formatDateTimeValue(salesStartAt)}</Text>
          </Pressable>
        </View>

        <View style={styles.timingCard}>
          <Text style={styles.timingLabel}>Sales end (optional)</Text>
          <Pressable style={styles.input} onPress={() => startDateTimeFlow('sales_end_at')}>
            <Text style={styles.pickerValue}>{formatDateTimeValue(salesEndAt)}</Text>
          </Pressable>
        </View>

        <Text style={styles.sectionTitle}>Venue / Location</Text>
        <TextInput style={styles.input} value={venueName} onChangeText={onChangeVenueName} placeholder="Venue name" placeholderTextColor={theme.colors.textSecondary} />
        {loadingVenueSuggestions ? <Text style={styles.hintText}>Searching venues…</Text> : null}
        {venueSuggestions.length > 0 ? (
          <View style={styles.suggestionsCard}>
            {venueSuggestions.map((venue) => (
              <Pressable key={venue.id} style={styles.suggestionItem} onPress={() => selectVenueSuggestion(venue)}>
                <Text style={styles.suggestionTitle}>{venue.name}</Text>
                {venue.address_text ? <Text style={styles.suggestionSubtitle}>{venue.address_text}</Text> : null}
              </Pressable>
            ))}
          </View>
        ) : null}
        <TextInput
          style={[styles.input, styles.multiline]}
          multiline
          numberOfLines={3}
          value={addressText}
          onChangeText={onChangeAddressText}
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

      {pickerSession ? (
        <Modal transparent animationType="fade" visible onRequestClose={cancelPickerSelection}>
          <View style={styles.modalBackdrop}>
            <Pressable style={StyleSheet.absoluteFill} onPress={cancelPickerSelection} />
            <View style={styles.modalCard}>
              <View style={styles.modalHeading}>
                <Text style={styles.modalTitle}>{getPickerTitle(pickerSession.field)}</Text>
                <Text style={styles.modalSubtitle}>{getPickerStepLabel(pickerSession)}</Text>
              </View>
              <View style={styles.modalActions}>
                <Pressable onPress={cancelPickerSelection}>
                  <Text style={styles.modalActionText}>Cancel</Text>
                </Pressable>
                <Pressable onPress={completePickerSelection}>
                  <Text style={styles.modalActionText}>Done</Text>
                </Pressable>
              </View>
              <View style={styles.pickerFrame}>
                <DateTimePicker
                  value={pickerDraftValue}
                  mode={pickerSession.mode}
                  onChange={(_, date) => {
                    if (date) setPickerDraftValue(date);
                  }}
                />
              </View>
            </View>
          </View>
        </Modal>
      ) : null}

      {isCategoryPickerVisible ? (
        <Modal transparent animationType="fade" visible onRequestClose={closeCategoryPicker}>
          <KeyboardAvoidingView
            style={styles.modalKeyboardAvoidingView}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          >
            <View style={[styles.modalBackdrop, styles.categoryModalBackdrop]}>
              <Pressable style={StyleSheet.absoluteFill} onPress={closeCategoryPicker} />
              <View style={[styles.modalCard, styles.categoryModalCard]}>
                <View style={styles.modalHeading}>
                  <Text style={styles.modalTitle}>Category</Text>
                  <Text style={styles.modalSubtitle}>Search or add a category</Text>
                </View>
                <View style={styles.modalActions}>
                  <Pressable onPress={closeCategoryPicker}>
                    <Text style={styles.modalActionText}>Done</Text>
                  </Pressable>
                </View>
                <View style={styles.categoryPickerBody}>
                  <TextInput
                    style={styles.input}
                    value={categorySearch}
                    onChangeText={setCategorySearch}
                    placeholder="Search categories"
                    placeholderTextColor={theme.colors.textSecondary}
                    autoCapitalize="words"
                    autoCorrect={false}
                  />

                  {trimmedCategorySearch ? (
                    <Pressable
                      style={styles.categoryOption}
                      onPress={() => selectCategory(exactMatchedCategoryOption ?? trimmedCategorySearch)}
                    >
                      <Text style={styles.categoryOptionText}>
                        {exactMatchedCategoryOption ? `Use “${exactMatchedCategoryOption}”` : `Add “${trimmedCategorySearch}” as category`}
                      </Text>
                    </Pressable>
                  ) : null}

                  <ScrollView
                    style={styles.categoryOptionsList}
                    keyboardShouldPersistTaps="handled"
                    keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
                  >
                    {filteredCategoryOptions.map((option) => (
                      <Pressable key={option} style={styles.categoryOption} onPress={() => selectCategory(option)}>
                        <Text style={styles.categoryOptionText}>{option}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                </View>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>
      ) : null}
    </>
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
  timingCard: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
    backgroundColor: theme.colors.surfaceElevated,
  },
  timingLabel: { color: theme.colors.textPrimary, fontWeight: '700' },
  pickerValue: { color: theme.colors.textPrimary },
  placeholderValue: { color: theme.colors.textSecondary },
  hintText: { color: theme.colors.textSecondary, fontSize: 12 },
  suggestionsCard: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surfaceElevated,
  },
  suggestionItem: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  suggestionTitle: { color: theme.colors.textPrimary, fontWeight: '600' },
  suggestionSubtitle: { color: theme.colors.textSecondary, marginTop: 2, fontSize: 12 },
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
  modalBackdrop: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.65)',
    padding: theme.spacing.lg,
  },
  modalKeyboardAvoidingView: {
    flex: 1,
  },
  categoryModalBackdrop: {
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: theme.colors.surfaceElevated,
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    width: '100%',
    maxWidth: 420,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.35,
    shadowRadius: 24,
    elevation: 10,
  },
  categoryModalCard: {
    maxHeight: '82%',
  },
  modalHeading: {
    paddingHorizontal: theme.spacing.lg,
    paddingTop: theme.spacing.lg,
    gap: 4,
  },
  modalTitle: {
    color: theme.colors.textPrimary,
    fontSize: 20,
    fontWeight: '700',
  },
  modalSubtitle: {
    color: theme.colors.textSecondary,
    fontSize: 13,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    marginTop: theme.spacing.sm,
  },
  modalActionText: {
    color: theme.colors.primary,
    fontWeight: '700',
    fontSize: 16,
  },
  pickerFrame: {
    alignItems: 'center',
    paddingVertical: theme.spacing.md,
  },
  categoryPickerBody: {
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
    flexShrink: 1,
  },
  categoryOptionsList: {
    maxHeight: 280,
    flexShrink: 1,
  },
  categoryOption: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  categoryOptionText: {
    color: theme.colors.textPrimary,
    fontWeight: '600',
  },
});
