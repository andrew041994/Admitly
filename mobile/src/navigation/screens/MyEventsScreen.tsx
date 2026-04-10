import { useEffect, useState } from 'react';
import { Alert, FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import {
  cancelOrganizerEvent,
  listOrganizerEvents,
  OrganizerEventDashboardItem,
  publishOrganizerEvent,
  unpublishOrganizerEvent,
} from '../../api/organizer';
import { theme } from '../../theme';

const getOrganizerStatusLabel = (event: OrganizerEventDashboardItem): string => {
  if (event.status === 'published' && event.approval_status !== 'approved') {
    return 'Published • Pending approval';
  }
  if (event.status === 'published' && event.approval_status === 'approved') {
    return 'Published • Publicly visible';
  }
  return event.status;
};

export function MyEventsScreen({ onOpenEvent }: { onOpenEvent: (eventId: number) => void }) {
  const [events, setEvents] = useState<OrganizerEventDashboardItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    listOrganizerEvents().then(setEvents).catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load events.'));

  useEffect(() => {
    load();
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
            <Text style={styles.meta}>{new Date(item.start_at).toLocaleString()} • {item.venue_name ?? 'Venue TBA'}</Text>
            <Text style={styles.meta}>Status: {getOrganizerStatusLabel(item)}</Text>
            {item.status === 'published' && item.approval_status !== 'approved' ? (
              <Text style={styles.helper}>This event is published but will not appear in discovery until approved.</Text>
            ) : null}
            <Text style={styles.meta}>Sold: {item.sold_count} • Revenue: {item.gross_revenue.toFixed(2)}</Text>
            <View style={styles.actions}>
              {(item.status === 'draft' || item.status === 'unpublished') ? (
                <Pressable
                  style={styles.actionButton}
                  onPress={() =>
                    publishOrganizerEvent(item.id).then((updatedEvent) => {
                      if (updatedEvent.approval_status === 'approved') {
                        Alert.alert('Event published', 'Your event is now published.');
                      } else {
                        Alert.alert('Event published', 'Event published and submitted for approval.');
                      }
                      return load();
                    })
                  }
                >
                  <Text style={styles.actionText}>Publish</Text>
                </Pressable>
              ) : null}
              {item.status === 'published' ? (
                <Pressable style={styles.actionButton} onPress={() => unpublishOrganizerEvent(item.id).then(load)}>
                  <Text style={styles.actionText}>Unpublish</Text>
                </Pressable>
              ) : null}
              {item.status !== 'cancelled' ? (
                <Pressable style={styles.actionButton} onPress={() => cancelOrganizerEvent(item.id).then(load)}>
                  <Text style={styles.actionText}>Cancel</Text>
                </Pressable>
              ) : null}
            </View>
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
  actions: { flexDirection: 'row', marginTop: theme.spacing.sm },
  helper: { color: theme.colors.textSecondary, marginTop: 4, fontStyle: 'italic' },
  actionButton: { borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, paddingVertical: 6, paddingHorizontal: 10, marginRight: theme.spacing.sm },
  actionText: { color: theme.colors.textPrimary, fontWeight: '600' },
  error: { color: theme.colors.error, marginBottom: theme.spacing.sm },
});
