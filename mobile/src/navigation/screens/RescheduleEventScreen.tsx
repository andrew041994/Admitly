import DateTimePicker, { DateTimePickerAndroid } from '@react-native-community/datetimepicker';
import type { DateTimePickerEvent } from '@react-native-community/datetimepicker';
import { useEffect, useMemo, useState } from 'react';
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../api/client';
import {
  EventReschedulePayload,
  OrganizerEventDetail,
  VenueSearchItem,
  getOrganizerEvent,
  rescheduleOrganizerEvent,
  searchVenues,
} from '../../api/organizer';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

type ScheduleField = 'start_at' | 'end_at' | 'doors_open_at' | 'sales_start_at' | 'sales_end_at';
type ScheduleValues = Record<ScheduleField, Date | null>;

const FIELD_LABELS: Record<ScheduleField, string> = {
  start_at: 'Event starts',
  end_at: 'Event ends',
  doors_open_at: 'Doors open',
  sales_start_at: 'Ticket sales start',
  sales_end_at: 'Ticket sales end',
};

function formatDate(value: Date | null): string {
  if (!value) return 'Not set';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(value);
}

function createRequestKey(eventId: number): string {
  return `reschedule-${eventId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function scheduleFromEvent(event: OrganizerEventDetail): ScheduleValues {
  return {
    start_at: new Date(event.start_at),
    end_at: new Date(event.end_at),
    doors_open_at: event.doors_open_at ? new Date(event.doors_open_at) : null,
    sales_start_at: event.sales_start_at ? new Date(event.sales_start_at) : null,
    sales_end_at: event.sales_end_at ? new Date(event.sales_end_at) : null,
  };
}

export function RescheduleEventScreen({ eventId, onCompleted }: { eventId: number; onCompleted: () => void }) {
  const [event, setEvent] = useState<OrganizerEventDetail | null>(null);
  const [schedule, setSchedule] = useState<ScheduleValues | null>(null);
  const [reason, setReason] = useState('');
  const [venueName, setVenueName] = useState('');
  const [addressText, setAddressText] = useState('');
  const [selectedVenueId, setSelectedVenueId] = useState<number | null>(null);
  const [venueSuggestions, setVenueSuggestions] = useState<VenueSearchItem[]>([]);
  const [loadingVenues, setLoadingVenues] = useState(false);
  const [latitude, setLatitude] = useState<string | null>(null);
  const [longitude, setLongitude] = useState<string | null>(null);
  const [isLocationPinned, setIsLocationPinned] = useState(false);
  const [pickerField, setPickerField] = useState<ScheduleField | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOrganizerEvent(eventId)
      .then((detail) => {
        setEvent(detail);
        setSchedule(scheduleFromEvent(detail));
        setSelectedVenueId(detail.venue_id);
        setVenueName(detail.venue_name ?? detail.custom_venue_name ?? '');
        setAddressText(detail.venue_address_text ?? detail.custom_address_text ?? '');
        setLatitude(detail.latitude);
        setLongitude(detail.longitude);
        setIsLocationPinned(detail.is_location_pinned);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load the event schedule.'));
  }, [eventId]);

  const trimmedVenueName = venueName.trim();
  useEffect(() => {
    let cancelled = false;
    if (trimmedVenueName.length < 2 || selectedVenueId !== null) {
      setVenueSuggestions([]);
      return () => { cancelled = true; };
    }
    const timeout = setTimeout(async () => {
      setLoadingVenues(true);
      try {
        const results = await searchVenues(trimmedVenueName, 8);
        if (!cancelled) setVenueSuggestions(results);
      } catch {
        if (!cancelled) setVenueSuggestions([]);
      } finally {
        if (!cancelled) setLoadingVenues(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(timeout); };
  }, [selectedVenueId, trimmedVenueName]);

  const pickerValue = useMemo(() => {
    if (!schedule || !pickerField) return new Date();
    return schedule[pickerField] ?? new Date();
  }, [pickerField, schedule]);

  function setField(field: ScheduleField, value: Date | null) {
    setSchedule((current) => current ? { ...current, [field]: value } : current);
    setError(null);
  }

  function markVenueAsCustom() {
    setSelectedVenueId(null);
    setLatitude(null);
    setLongitude(null);
    setIsLocationPinned(false);
  }

  function selectVenue(venue: VenueSearchItem) {
    setSelectedVenueId(venue.id);
    setVenueName(venue.name);
    setAddressText(venue.address_text ?? '');
    setVenueSuggestions([]);
    setLatitude(null);
    setLongitude(null);
    setIsLocationPinned(false);
    setError(null);
  }

  function openPicker(field: ScheduleField) {
    const initial = schedule?.[field] ?? new Date();
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value: initial,
        mode: 'date',
        onChange: (dateEvent, selectedDate) => {
          if (dateEvent.type !== 'set' || !selectedDate) return;
          DateTimePickerAndroid.open({
            value: selectedDate,
            mode: 'time',
            onChange: (timeEvent, selectedTime) => {
              if (timeEvent.type !== 'set' || !selectedTime) return;
              const combined = new Date(selectedDate);
              combined.setHours(selectedTime.getHours(), selectedTime.getMinutes(), 0, 0);
              setField(field, combined);
            },
          });
        },
      });
      return;
    }
    setPickerField(field);
  }

  function onPickerChange(event: DateTimePickerEvent, value?: Date) {
    if (event.type === 'set' && value && pickerField) setField(pickerField, value);
  }

  async function submit() {
    if (!event || !schedule?.start_at || !schedule.end_at) return;
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      setError('Enter a reason for the reschedule audit record.');
      return;
    }
    if (!trimmedVenueName) {
      setError('Select a venue or enter a custom venue name.');
      return;
    }
    const idempotencyKey = requestKey ?? createRequestKey(eventId);
    setRequestKey(idempotencyKey);
    setLoading(true);
    setError(null);
    const payload: EventReschedulePayload = {
      idempotency_key: idempotencyKey,
      start_at: schedule.start_at.toISOString(),
      end_at: schedule.end_at.toISOString(),
      doors_open_at: schedule.doors_open_at?.toISOString() ?? null,
      sales_start_at: schedule.sales_start_at?.toISOString() ?? null,
      sales_end_at: schedule.sales_end_at?.toISOString() ?? null,
      venue_id: selectedVenueId,
      custom_venue_name: selectedVenueId === null ? trimmedVenueName : null,
      custom_address_text: selectedVenueId === null ? addressText.trim() || null : null,
      latitude: latitude,
      longitude: longitude,
      is_location_pinned: isLocationPinned,
      reason: trimmedReason,
    };
    try {
      await rescheduleOrganizerEvent(eventId, payload);
      onCompleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to reschedule the event. Retry with the same schedule.');
    } finally {
      setLoading(false);
    }
  }

  if (!event || !schedule) {
    return <Screen><Text style={error ? styles.error : styles.meta}>{error ?? 'Loading event schedule…'}</Text></Screen>;
  }

  if (event.approval_status !== 'approved') {
    return <Screen><Text style={styles.error}>Only approved events use the dedicated reschedule workflow.</Text></Screen>;
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>Reschedule or Change Venue</Text>
        <Text style={styles.eventTitle}>{event.title}</Text>
        <Text style={styles.meta}>Times are shown in your device timezone. The event timezone remains {event.timezone}.</Text>
        <Text style={styles.notice}>Existing tickets and check-in codes remain valid. Ticket holders will be notified when tickets have been issued.</Text>
        {(Object.keys(FIELD_LABELS) as ScheduleField[]).map((field) => (
          <View key={field} style={styles.field}>
            <Text style={styles.label}>{FIELD_LABELS[field]}</Text>
            <Pressable accessibilityRole="button" accessibilityLabel={`Change ${FIELD_LABELS[field]}`} style={styles.dateButton} onPress={() => openPicker(field)}>
              <Text style={styles.dateText}>{formatDate(schedule[field])}</Text>
            </Pressable>
            {field !== 'start_at' && field !== 'end_at' && schedule[field] ? (
              <Pressable accessibilityRole="button" onPress={() => setField(field, null)}><Text style={styles.clear}>Clear</Text></Pressable>
            ) : null}
          </View>
        ))}
        <Text style={styles.sectionTitle}>Venue</Text>
        <View style={styles.currentVenue}>
          <Text style={styles.label}>Current venue</Text>
          <Text style={styles.meta}>{event.venue_name ?? event.custom_venue_name ?? 'Not set'}</Text>
          <Text style={styles.meta}>{event.venue_address_text ?? event.custom_address_text ?? 'Address not provided'}</Text>
        </View>
        <Text style={styles.label}>New venue</Text>
        <TextInput
          accessibilityLabel="New venue name"
          value={venueName}
          onChangeText={(value) => { setVenueName(value); markVenueAsCustom(); setError(null); }}
          placeholder="Venue name"
          placeholderTextColor={theme.colors.textSecondary}
          style={styles.inputSingle}
        />
        {loadingVenues ? <Text style={styles.meta}>Searching venues…</Text> : null}
        {venueSuggestions.length ? (
          <View style={styles.suggestions}>
            {venueSuggestions.map((venue) => (
              <Pressable key={venue.id} accessibilityRole="button" onPress={() => selectVenue(venue)} style={styles.suggestion}>
                <Text style={styles.label}>{venue.name}</Text>
                {venue.address_text ? <Text style={styles.meta}>{venue.address_text}</Text> : null}
              </Pressable>
            ))}
          </View>
        ) : null}
        <TextInput
          accessibilityLabel="New venue address"
          value={addressText}
          onChangeText={(value) => { setAddressText(value); markVenueAsCustom(); setError(null); }}
          multiline
          placeholder="Address"
          placeholderTextColor={theme.colors.textSecondary}
          style={styles.input}
        />
        <Text style={styles.label}>Reason for rescheduling</Text>
        <TextInput
          accessibilityLabel="Reason for rescheduling"
          value={reason}
          onChangeText={(value) => { setReason(value); setError(null); }}
          multiline
          maxLength={1000}
          placeholder="Explain why the event schedule changed"
          placeholderTextColor={theme.colors.textSecondary}
          style={styles.input}
        />
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        <ThemedButton label="Confirm reschedule" onPress={submit} loading={loading} disabled={loading} />
      </ScrollView>
      {pickerField && Platform.OS !== 'android' ? (
        <Modal transparent animationType="fade" visible onRequestClose={() => setPickerField(null)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.modalCard}>
              <Text style={styles.label}>{FIELD_LABELS[pickerField]}</Text>
              <DateTimePicker value={pickerValue} mode="datetime" onChange={onPickerChange} />
              <ThemedButton label="Done" onPress={() => setPickerField(null)} />
            </View>
          </View>
        </Modal>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { gap: theme.spacing.md, paddingBottom: theme.spacing.xl },
  title: { color: theme.colors.textPrimary, fontSize: theme.typography.heading, fontWeight: '700' },
  eventTitle: { color: theme.colors.primary, fontSize: theme.typography.body, fontWeight: '700' },
  sectionTitle: { color: theme.colors.textPrimary, fontSize: 18, fontWeight: '700', marginTop: theme.spacing.sm },
  meta: { color: theme.colors.textSecondary },
  notice: { color: theme.colors.textPrimary, backgroundColor: theme.colors.surface, borderRadius: theme.radius.md, borderWidth: 1, borderColor: theme.colors.primaryMuted, padding: theme.spacing.md },
  field: { gap: theme.spacing.xs },
  label: { color: theme.colors.textPrimary, fontWeight: '700' },
  dateButton: { borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, padding: theme.spacing.md, backgroundColor: theme.colors.surface },
  dateText: { color: theme.colors.textPrimary },
  clear: { color: theme.colors.primary, fontWeight: '600' },
  input: { minHeight: 100, textAlignVertical: 'top', color: theme.colors.textPrimary, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, padding: theme.spacing.md },
  inputSingle: { color: theme.colors.textPrimary, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, padding: theme.spacing.md },
  currentVenue: { gap: theme.spacing.xs, backgroundColor: theme.colors.surface, borderRadius: theme.radius.md, padding: theme.spacing.md },
  suggestions: { borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, overflow: 'hidden' },
  suggestion: { gap: 2, padding: theme.spacing.md, borderBottomWidth: 1, borderBottomColor: theme.colors.border },
  error: { color: theme.colors.error },
  modalBackdrop: { flex: 1, justifyContent: 'center', padding: theme.spacing.lg, backgroundColor: 'rgba(0,0,0,0.7)' },
  modalCard: { gap: theme.spacing.md, borderRadius: theme.radius.lg, backgroundColor: theme.colors.surface, padding: theme.spacing.lg },
});
