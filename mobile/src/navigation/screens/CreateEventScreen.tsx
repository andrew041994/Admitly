import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../api/client';
import { createEvent } from '../../api/organizer';
import { theme } from '../../theme';

export function CreateEventScreen({ onCreated }: { onCreated: (eventId: number) => void }) {
  const [title, setTitle] = useState('');
  const [shortDescription, setShortDescription] = useState('');
  const [venueName, setVenueName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const start = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
      const end = new Date(Date.now() + 26 * 60 * 60 * 1000).toISOString();
      const created = await createEvent({
        title,
        short_description: shortDescription,
        long_description: shortDescription,
        start_at: start,
        end_at: end,
        timezone: 'UTC',
        custom_venue_name: venueName,
        custom_address_text: venueName,
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to create event.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Create Event</Text>
      <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="Event title" placeholderTextColor={theme.colors.textSecondary} />
      <TextInput style={styles.input} value={shortDescription} onChangeText={setShortDescription} placeholder="Short description" placeholderTextColor={theme.colors.textSecondary} />
      <TextInput style={styles.input} value={venueName} onChangeText={setVenueName} placeholder="Venue name" placeholderTextColor={theme.colors.textSecondary} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Pressable onPress={submit} style={styles.button} disabled={loading}>
        <Text style={styles.buttonText}>{loading ? 'Creating…' : 'Create Event'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: theme.spacing.lg, backgroundColor: theme.colors.background, gap: theme.spacing.sm },
  title: { color: theme.colors.textPrimary, fontSize: 22, fontWeight: '700' },
  input: { borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, color: theme.colors.textPrimary, padding: theme.spacing.md, backgroundColor: theme.colors.surface },
  button: { backgroundColor: theme.colors.primary, borderRadius: theme.radius.md, padding: theme.spacing.md, marginTop: theme.spacing.sm },
  buttonText: { color: '#111', fontWeight: '700', textAlign: 'center' },
  error: { color: theme.colors.error },
});
