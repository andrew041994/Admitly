import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { getAccountProfile } from '../../api/account';
import { ApiError } from '../../api/client';
import { theme } from '../../theme';

type Props = {
  onOpenCreateEvent: () => void;
  onOpenMyEvents: () => void;
  onOpenStaffManagement: () => void;
  onSignOut: () => void;
};

export function ProfileScreen({ onOpenCreateEvent, onOpenMyEvents, onOpenStaffManagement, onSignOut }: Props) {
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof getAccountProfile>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAccountProfile().then(setProfile).catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load profile.'));
  }, []);

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
          <Text style={styles.meta}>{profile.phone_number ?? 'No phone number added'}</Text>
          <Text style={styles.meta}>My tickets: {profile.my_tickets_count}</Text>
          <Text style={styles.meta}>My events: {profile.my_events_count}</Text>
          <Text style={styles.meta}>Staff events: {profile.staff_events_count}</Text>
        </View>
      ) : null}

      <Pressable style={styles.button} onPress={onOpenCreateEvent}><Text style={styles.buttonText}>Create Event</Text></Pressable>
      <Pressable style={styles.button} onPress={onOpenMyEvents}><Text style={styles.buttonText}>My Events</Text></Pressable>
      <Pressable style={styles.button} onPress={onOpenStaffManagement}><Text style={styles.buttonText}>Manage Staff</Text></Pressable>
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
  button: { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.md, padding: theme.spacing.md },
  buttonText: { color: theme.colors.textPrimary, fontWeight: '600' },
  signOut: { marginTop: theme.spacing.md },
  signOutText: { color: theme.colors.primary, fontWeight: '700' },
  error: { color: theme.colors.error },
});
