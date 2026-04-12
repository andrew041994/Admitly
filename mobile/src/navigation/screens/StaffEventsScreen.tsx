import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { listMyStaffEvents, StaffEvent } from '../../api/account';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

type Props = {
  onOpenScanner: (eventId: number, eventTitle: string) => void;
};

function formatEventDate(dateIso: string): string {
  const date = new Date(dateIso);
  if (Number.isNaN(date.getTime())) {
    return 'Date TBD';
  }
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

function formatEventTime(startAt: string, endAt: string | null): string {
  const start = new Date(startAt);
  if (Number.isNaN(start.getTime())) {
    return 'Time TBD';
  }

  const startLabel = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(start);

  if (!endAt) {
    return startLabel;
  }

  const end = new Date(endAt);
  if (Number.isNaN(end.getTime())) {
    return startLabel;
  }

  const endLabel = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(end);
  return `${startLabel} - ${endLabel}`;
}

export function StaffEventsScreen({ onOpenScanner }: Props) {
  const [events, setEvents] = useState<StaffEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadEvents = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const response = await listMyStaffEvents();
      setEvents(response);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Unable to load your staff events right now.';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  if (loading) {
    return (
      <View style={styles.stateWrap}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.stateText}>Loading your assigned events…</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.stateWrap}>
        <Text style={styles.errorText}>{error}</Text>
        <ThemedButton label="Try Again" variant="secondary" onPress={() => loadEvents()} />
      </View>
    );
  }

  if (events.length === 0) {
    return (
      <View style={styles.stateWrap}>
        <Text style={styles.stateText}>You’re not assigned to any events right now.</Text>
      </View>
    );
  }

  return (
    <FlatList
      data={events}
      keyExtractor={(item) => String(item.event_id)}
      contentContainerStyle={styles.listContent}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => loadEvents(true)}
          tintColor={theme.colors.primary}
        />
      }
      renderItem={({ item }) => (
        <View style={styles.card}>
          <Text style={styles.title}>{item.title}</Text>
          <Text style={styles.meta}>{formatEventDate(item.start_at)}</Text>
          <Text style={styles.meta}>{formatEventTime(item.start_at, item.end_at)}</Text>
          {item.venue_name ? <Text style={styles.meta}>Venue: {item.venue_name}</Text> : null}
          {item.role ? <Text style={styles.meta}>Role: {item.role}</Text> : null}
          <View style={styles.actionWrap}>
            <ThemedButton label="Scan Tickets" onPress={() => onOpenScanner(item.event_id, item.title)} />
          </View>
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  listContent: {
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing.md,
    gap: 4,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '700',
  },
  meta: {
    color: theme.colors.textSecondary,
  },
  actionWrap: {
    marginTop: theme.spacing.sm,
  },
  stateWrap: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.xl,
    gap: theme.spacing.md,
    backgroundColor: theme.colors.background,
  },
  stateText: {
    color: theme.colors.textSecondary,
    textAlign: 'center',
  },
  errorText: {
    color: theme.colors.error,
    textAlign: 'center',
  },
});
