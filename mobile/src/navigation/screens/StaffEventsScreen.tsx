import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { listMyStaffEvents, StaffEvent } from '../../api/account';
import { ThemedButton } from '../../components/ThemedButton';
import { theme } from '../../theme';

const DEFAULT_EVENT_TIMEZONE = 'America/Guyana';

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

type ScanAvailability = {
  canScan: boolean;
  status: 'upcoming' | 'live' | 'ended';
  buttonLabel: 'Scan Tickets' | 'Scanning Not Open Yet' | 'Event Ended';
  countdownLabel: string | null;
};

function getTimeParts(date: Date, timeZone: string) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const parts = formatter.formatToParts(date);
  const getPart = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return {
    year: getPart('year'),
    month: getPart('month'),
    day: getPart('day'),
    hour: getPart('hour'),
    minute: getPart('minute'),
    second: getPart('second'),
  };
}

function getLocalMidnightUtcMs(date: Date, timeZone: string) {
  const local = getTimeParts(date, timeZone);
  const targetLocalEpoch = Date.UTC(local.year, local.month - 1, local.day, 0, 0, 0);
  const utcGuess = targetLocalEpoch;
  const guessLocal = getTimeParts(new Date(utcGuess), timeZone);
  const guessLocalEpoch = Date.UTC(
    guessLocal.year,
    guessLocal.month - 1,
    guessLocal.day,
    guessLocal.hour,
    guessLocal.minute,
    guessLocal.second,
  );

  return utcGuess - (guessLocalEpoch - targetLocalEpoch);
}

function getScanAvailability(event: StaffEvent, nowMs: number): ScanAvailability {
  const start = new Date(event.start_at);
  if (Number.isNaN(start.getTime())) {
    return { canScan: false, status: 'upcoming', buttonLabel: 'Scanning Not Open Yet', countdownLabel: null };
  }

  const timeZone = event.timezone || DEFAULT_EVENT_TIMEZONE;
  const scanStartsAtMs = getLocalMidnightUtcMs(start, timeZone);

  const fallbackEnd = start.getTime();
  const end = event.end_at ? new Date(event.end_at) : null;
  const scanEndsAtMs = end && !Number.isNaN(end.getTime()) ? end.getTime() : fallbackEnd;

  if (nowMs < scanStartsAtMs) {
    return {
      canScan: false,
      status: 'upcoming',
      buttonLabel: 'Scanning Not Open Yet',
      countdownLabel: formatScanningCountdown(scanStartsAtMs - nowMs),
    };
  }

  if (nowMs > scanEndsAtMs) {
    return { canScan: false, status: 'ended', buttonLabel: 'Event Ended', countdownLabel: null };
  }

  return { canScan: true, status: 'live', buttonLabel: 'Scan Tickets', countdownLabel: null };
}

function formatScanningCountdown(msUntilScanOpen: number): string {
  const totalMinutes = Math.max(1, Math.ceil(msUntilScanOpen / 60000));
  if (totalMinutes < 60) {
    return `Scanning opens in ${totalMinutes} ${totalMinutes === 1 ? 'minute' : 'minutes'}`;
  }

  const totalHours = Math.ceil(totalMinutes / 60);
  if (totalHours < 48) {
    return `Scanning opens in ${totalHours} ${totalHours === 1 ? 'hour' : 'hours'}`;
  }

  const totalDays = Math.ceil(totalHours / 24);
  return `Scanning opens in ${totalDays} ${totalDays === 1 ? 'day' : 'days'}`;
}

function getStatusBadgeLabel(status: ScanAvailability['status']): string {
  if (status === 'upcoming') {
    return 'Upcoming';
  }
  if (status === 'ended') {
    return 'Ended';
  }
  return 'Live';
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
      renderItem={({ item }) => {
        const availability = getScanAvailability(item, Date.now());

        return (
          <View style={styles.card}>
            <View style={styles.titleRow}>
              <Text style={styles.title}>{item.title}</Text>
              <View
                style={[
                  styles.statusBadge,
                  availability.status === 'upcoming'
                    ? styles.statusBadgeUpcoming
                    : availability.status === 'live'
                      ? styles.statusBadgeLive
                      : styles.statusBadgeEnded,
                ]}
              >
                <Text style={styles.statusBadgeText}>{getStatusBadgeLabel(availability.status)}</Text>
              </View>
            </View>
            <Text style={styles.meta}>{formatEventDate(item.start_at)}</Text>
            <Text style={styles.meta}>{formatEventTime(item.start_at, item.end_at)}</Text>
            {item.venue_name ? <Text style={styles.meta}>Venue: {item.venue_name}</Text> : null}
            {item.role ? <Text style={styles.meta}>Role: {item.role}</Text> : null}
            {availability.countdownLabel ? <Text style={styles.countdownText}>{availability.countdownLabel}</Text> : null}
            <View style={styles.actionWrap}>
              <ThemedButton
                label={availability.buttonLabel}
                onPress={() => onOpenScanner(item.event_id, item.title)}
                disabled={!availability.canScan}
              />
            </View>
          </View>
        );
      }}
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
  titleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: theme.spacing.sm,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '700',
    flex: 1,
  },
  statusBadge: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 4,
    marginTop: 2,
  },
  statusBadgeUpcoming: {
    borderColor: theme.colors.primaryMuted,
    backgroundColor: '#1A1609',
  },
  statusBadgeLive: {
    borderColor: theme.colors.success,
    backgroundColor: 'rgba(52,199,89,0.18)',
  },
  statusBadgeEnded: {
    borderColor: theme.colors.border,
    backgroundColor: '#171717',
  },
  statusBadgeText: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.caption,
    fontWeight: '700',
  },
  meta: {
    color: theme.colors.textSecondary,
  },
  countdownText: {
    color: '#EFE3B2',
    fontSize: theme.typography.label,
    marginTop: 2,
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
