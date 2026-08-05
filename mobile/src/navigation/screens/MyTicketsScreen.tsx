import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import {
  TicketTransfer,
  WalletTicketCard,
  acceptTicketTransfer,
  cancelTicketTransfer,
  declineTicketTransfer,
  listMyTicketTransfers,
  listMyTickets,
} from '../../api/tickets';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { isPendingTransfer } from '../../features/transfers/validation';
import { theme } from '../../theme';

type MyTicketsScreenProps = {
  onOpenTicket: (ticketId: number) => void;
};

function formatDate(iso: string): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function statusLabel(status: string): string {
  if (status === 'active') return 'Active';
  if (status === 'used') return 'Used';
  if (status === 'invalid') return 'Invalid';
  return status;
}

export function MyTicketsScreen({ onOpenTicket }: MyTicketsScreenProps) {
  const [tickets, setTickets] = useState<WalletTicketCard[]>([]);
  const [transfers, setTransfers] = useState<TicketTransfer[]>([]);
  const [actingId, setActingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true);
    try {
      const [ticketData, transferData] = await Promise.all([
        listMyTickets(),
        listMyTicketTransfers(),
      ]);
      setTickets(ticketData);
      setTransfers(transferData);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load your tickets.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const pendingTransfers = transfers.filter((transfer) => isPendingTransfer(transfer.status));

  async function act(transfer: TicketTransfer, action: 'accept' | 'decline' | 'cancel') {
    if (actingId !== null) return;
    setActingId(transfer.id);
    setError(null);
    try {
      if (action === 'accept') await acceptTicketTransfer(transfer.id);
      else if (action === 'decline') await declineTicketTransfer(transfer.id);
      else await cancelTicketTransfer(transfer.id);
      await loadTickets(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to update the transfer. Check your connection and try again.');
    } finally {
      setActingId(null);
    }
  }

  useEffect(() => {
    loadTickets();
  }, [loadTickets]);

  const grouped = useMemo(() => ({
    upcoming: tickets.filter((t) => t.event.is_upcoming),
    past: tickets.filter((t) => !t.event.is_upcoming),
  }), [tickets]);

  if (loading) {
    return <Screen><View style={styles.stateWrap}><ActivityIndicator color={theme.colors.primary} /><Text style={styles.stateText}>Loading your wallet...</Text></View></Screen>;
  }

  if (error) {
    return <Screen><View style={styles.stateWrap}><Text style={styles.errorText}>{error}</Text><ThemedButton label="Try again" onPress={() => loadTickets()} /></View></Screen>;
  }

  if (tickets.length === 0 && pendingTransfers.length === 0) {
    return (
      <Screen>
        <View style={styles.stateWrap}>
          <Text style={styles.stateTitle}>No tickets yet</Text>
          <Text style={styles.stateText}>When you buy tickets, they will appear in your wallet.</Text>
        </View>
      </Screen>
    );
  }

  return (
    <Screen padded={false}>
      <FlatList
        data={[{ key: 'Upcoming', items: grouped.upcoming }, { key: 'Past', items: grouped.past }]}
        keyExtractor={(item) => item.key}
        contentContainerStyle={styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadTickets(true)} tintColor={theme.colors.primary} />}
        ListHeaderComponent={pendingTransfers.length ? (
          <View style={styles.transferSection}>
            <Text style={styles.sectionTitle}>Ticket transfers</Text>
            {pendingTransfers.map((transfer) => (
              <View key={transfer.id} style={styles.transferCard}>
                <Text style={styles.title}>{transfer.event_title}</Text>
                <Text style={styles.meta}>{transfer.ticket_tier_name} • {formatDate(transfer.starts_at)}</Text>
                <Text style={styles.meta}>{transfer.direction === 'incoming' ? 'From an Admitly ticket owner' : `To ${transfer.recipient_identifier}`}</Text>
                <Text style={styles.pending}>Pending acceptance</Text>
                {transfer.direction === 'incoming' ? (
                  <View style={styles.actionRow}>
                    <View style={styles.action}><ThemedButton label="Accept" onPress={() => act(transfer, 'accept')} loading={actingId === transfer.id} disabled={actingId !== null} /></View>
                    <View style={styles.action}><ThemedButton label="Decline" variant="secondary" onPress={() => act(transfer, 'decline')} disabled={actingId !== null} /></View>
                  </View>
                ) : (
                  <ThemedButton label="Cancel transfer" variant="secondary" onPress={() => act(transfer, 'cancel')} loading={actingId === transfer.id} disabled={actingId !== null} />
                )}
              </View>
            ))}
          </View>
        ) : null}
        renderItem={({ item }) => (
          <View>
            {item.items.length > 0 && <Text style={styles.sectionTitle}>{item.key}</Text>}
            {item.items.map((ticket) => (
              <Pressable key={ticket.id} style={styles.card} onPress={() => onOpenTicket(ticket.id)}>
                <View style={styles.row}><Text style={styles.title}>{ticket.event.title}</Text><Text style={[styles.badge, ticket.display_status === 'active' ? styles.badgeActive : styles.badgeMuted]}>{statusLabel(ticket.display_status)}</Text></View>
                <Text style={styles.meta}>{formatDate(ticket.event.start_at)}</Text>
                <Text style={styles.meta}>{ticket.venue.name ?? ticket.venue.address_summary ?? 'Venue TBA'}</Text>
                <Text style={styles.meta}>{ticket.ticket_tier_name} • {ticket.manual_code_display}</Text>
                <Text style={styles.link}>View Ticket</Text>
              </Pressable>
            ))}
          </View>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  listContent: { padding: theme.spacing.lg, gap: theme.spacing.md },
  sectionTitle: { color: theme.colors.textPrimary, fontWeight: '700', marginBottom: theme.spacing.sm, fontSize: theme.typography.body },
  card: { backgroundColor: theme.colors.surface, borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.lg, padding: theme.spacing.md, gap: theme.spacing.xs, marginBottom: theme.spacing.sm },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: theme.spacing.sm, alignItems: 'center' },
  title: { color: theme.colors.textPrimary, fontWeight: '700', flex: 1 },
  meta: { color: theme.colors.textSecondary, fontSize: theme.typography.caption },
  link: { color: theme.colors.primary, fontWeight: '600', marginTop: theme.spacing.xs },
  badge: { borderRadius: 999, paddingHorizontal: theme.spacing.sm, paddingVertical: 2, fontSize: theme.typography.caption, overflow: 'hidden' },
  badgeActive: { backgroundColor: '#1f2c13', color: '#98e067' },
  badgeMuted: { backgroundColor: '#2a2a2a', color: theme.colors.textSecondary },
  stateWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: theme.spacing.md, padding: theme.spacing.lg },
  stateTitle: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: theme.typography.heading },
  stateText: { color: theme.colors.textSecondary, textAlign: 'center' },
  errorText: { color: theme.colors.error, textAlign: 'center' },
  transferSection: { gap: theme.spacing.sm, marginBottom: theme.spacing.md },
  transferCard: { backgroundColor: theme.colors.surface, borderWidth: 1, borderColor: theme.colors.primaryMuted, borderRadius: theme.radius.lg, padding: theme.spacing.md, gap: theme.spacing.xs },
  pending: { color: theme.colors.primary, fontWeight: '700', marginTop: theme.spacing.xs },
  actionRow: { flexDirection: 'row', gap: theme.spacing.sm, marginTop: theme.spacing.sm },
  action: { flex: 1 },
});
