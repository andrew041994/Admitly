import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { getAccountProfile, updateAccountProfile } from '../../api/account';
import { ApiError } from '../../api/client';
import { ThemedButton } from '../../components/ThemedButton';
import { normalizePhoneNumber } from '../../features/transfers/validation';
import { theme } from '../../theme';

type Props = {
  onOpenCreateEvent: () => void;
  onOpenMyEvents: () => void;
  onOpenStaffManagement: () => void;
  onOpenStaffEvents: () => void;
  onSignOut: () => void;
};

export function ProfileScreen({ onOpenCreateEvent, onOpenMyEvents, onOpenStaffManagement, onOpenStaffEvents, onSignOut }: Props) {
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getAccountProfile>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    getAccountProfile().then((data) => {
      setProfile(data);
      setPhoneNumber(data.phone_number ?? '');
    }).catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load profile.'));
  }, []);

  async function savePhone() {
    if (!profile) return;
    const normalized = normalizePhoneNumber(phoneNumber);
    if (!normalized) {
      setError('Enter a valid Guyana number or an international number with country code.');
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      await updateAccountProfile(profile.full_name, normalized);
      const refreshed = await getAccountProfile();
      setProfile(refreshed);
      setPhoneNumber(refreshed.phone_number ?? '');
      setSaved('Phone number saved. Phone transfers remain unavailable until phone verification is introduced.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save phone number.');
    } finally {
      setSaving(false);
    }
  }

  if (!profile && !error) {
    return <ActivityIndicator color={theme.colors.primary} style={{ marginTop: 36 }} />;
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Profile</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {profile ? (
        <View style={styles.card}>
          <Text style={styles.name}>{profile.full_name}</Text>
          <Text style={styles.meta}>{profile.email}</Text>
          <TextInput
            accessibilityLabel="Phone number"
            value={phoneNumber}
            onChangeText={setPhoneNumber}
            keyboardType="phone-pad"
            placeholder="Phone number"
            placeholderTextColor={theme.colors.textSecondary}
            style={styles.input}
          />
          <Text style={styles.meta}>{profile.phone_is_verified ? 'Phone verified' : 'Phone not verified'}</Text>
          <ThemedButton label="Save phone" onPress={savePhone} loading={saving} disabled={saving} />
          {saved ? <Text style={styles.success}>{saved}</Text> : null}
          <Text style={styles.meta}>My tickets: {profile.my_tickets_count}</Text>
          <Text style={styles.meta}>My events: {profile.my_events_count}</Text>
          <Text style={styles.meta}>Staff events: {profile.staff_events_count}</Text>
        </View>
      ) : null}

      <Text style={styles.sectionLabel}>Organizer</Text>
      <Pressable style={styles.button} onPress={onOpenCreateEvent}>
        <Text style={styles.buttonText}>Create Event</Text>
        <Text style={styles.chevron}>›</Text>
      </Pressable>
      <Pressable style={styles.button} onPress={onOpenMyEvents}>
        <Text style={styles.buttonText}>My Events</Text>
        <Text style={styles.chevron}>›</Text>
      </Pressable>
      <Pressable style={styles.button} onPress={onOpenStaffManagement}>
        <Text style={styles.buttonText}>Manage Staff</Text>
        <Text style={styles.chevron}>›</Text>
      </Pressable>

      <Text style={styles.sectionLabel}>Staff</Text>
      <Pressable style={styles.button} onPress={onOpenStaffEvents}>
        <Text style={styles.buttonText}>Events I’m Working</Text>
        <Text style={styles.chevron}>›</Text>
      </Pressable>
      <Pressable style={styles.signOut} onPress={onSignOut}><Text style={styles.signOutText}>Logout</Text></Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background, padding: theme.spacing.lg, gap: theme.spacing.sm },
  title: { color: theme.colors.textPrimary, fontSize: 24, fontWeight: '700' },
  card: { backgroundColor: theme.colors.surface, borderRadius: theme.radius.md, padding: theme.spacing.md, gap: 6 },
  name: { color: theme.colors.textPrimary, fontSize: 18, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary },
  sectionLabel: { color: theme.colors.textSecondary, fontSize: 13, fontWeight: '700', marginTop: theme.spacing.sm },
  button: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  buttonText: { color: theme.colors.textPrimary, fontWeight: '600' },
  chevron: { color: '#B8B1A1', fontSize: 18, fontWeight: '600', lineHeight: 18 },
  signOut: { marginTop: theme.spacing.md },
  signOutText: { color: theme.colors.primary, fontWeight: '700' },
  error: { color: theme.colors.error },
  success: { color: '#98e067' },
  input: { color: theme.colors.textPrimary, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, paddingHorizontal: theme.spacing.sm, paddingVertical: 10 },
});
