import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { listMyEvents, MyEventItem } from '../../api/organizer';
import { theme } from '../../theme';

export function MyEventsScreen({ onOpenEvent }: { onOpenEvent: (eventId: number) => void }) {
  const [events, setEvents] = useState<MyEventItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMyEvents().then(setEvents).catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load events.'));
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>My Events</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={events}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <Pressable style={styles.item} onPress={() => onOpenEvent(item.id)}>
            <Text style={styles.itemTitle}>{item.title}</Text>
            <Text style={styles.meta}>{new Date(item.start_at).toLocaleString()} • {item.is_active ? 'Active' : 'Ended'}</Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: theme.spacing.lg, backgroundColor: theme.colors.background },
  title: { color: theme.colors.textPrimary, fontSize: 22, fontWeight: '700', marginBottom: theme.spacing.md },
  item: { backgroundColor: theme.colors.surface, borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, padding: theme.spacing.md, marginBottom: theme.spacing.sm },
  itemTitle: { color: theme.colors.textPrimary, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary, marginTop: 4 },
  error: { color: theme.colors.error, marginBottom: theme.spacing.sm },
});
