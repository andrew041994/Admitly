import { useEffect, useState } from 'react';
import { FlatList, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { getEventDashboard } from '../../api/organizer';
import { theme } from '../../theme';

export function OrganizerDashboardScreen({ eventId }: { eventId: number }) {
  const [dashboard, setDashboard] = useState<Awaited<ReturnType<typeof getEventDashboard>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEventDashboard(eventId).then(setDashboard).catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load dashboard.'));
  }, [eventId]);

  if (!dashboard) {
    return <View style={styles.container}><Text style={styles.meta}>{error ?? 'Loading dashboard…'}</Text></View>;
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Event Dashboard</Text>
      <Text style={styles.metric}>Tickets sold: {dashboard.tickets_sold}</Text>
      <Text style={styles.metric}>Gross revenue: {dashboard.gross_revenue.toFixed(2)}</Text>
      <Text style={styles.metric}>Admitted: {dashboard.attendees_admitted}</Text>
      <Text style={styles.metric}>Remaining: {dashboard.attendees_remaining}</Text>
      <Text style={styles.metric}>Active staff: {dashboard.active_staff_assigned}</Text>
      <Text style={styles.section}>Tier metrics</Text>
      <FlatList
        data={dashboard.tier_metrics}
        keyExtractor={(item) => String(item.ticket_tier_id)}
        renderItem={({ item }) => <Text style={styles.meta}>{item.name}: sold {item.sold_count}, remaining {item.remaining_count}</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background, padding: theme.spacing.lg },
  title: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: 22, marginBottom: theme.spacing.sm },
  metric: { color: theme.colors.textPrimary, marginBottom: 4 },
  section: { color: theme.colors.textSecondary, marginTop: theme.spacing.md, marginBottom: theme.spacing.xs },
  meta: { color: theme.colors.textSecondary, marginBottom: 4 },
});
