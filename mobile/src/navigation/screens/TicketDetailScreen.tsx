import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { WalletTicketDetail, getMyTicket, getMyTicketQr } from '../../api/tickets';
import { Screen } from '../../components/Screen';
import { theme } from '../../theme';

type TicketDetailScreenProps = {
  ticketId: number;
};

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'short' }).format(new Date(iso));
}

export function TicketDetailScreen({ ticketId }: TicketDetailScreenProps) {
  const [ticket, setTicket] = useState<WalletTicketDetail | null>(null);
  const [qrDataUri, setQrDataUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getMyTicket(ticketId), getMyTicketQr(ticketId)])
      .then(([ticketData, qrData]) => {
        setTicket(ticketData);
        setQrDataUri(qrData.qr_data_uri);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load ticket.'));
  }, [ticketId]);

  if (error) return <Screen><View style={styles.stateWrap}><Text style={styles.error}>{error}</Text></View></Screen>;
  if (!ticket) return <Screen><View style={styles.stateWrap}><ActivityIndicator color={theme.colors.primary} /></View></Screen>;

  return (
    <Screen>
      <View style={styles.container}>
        <Text style={styles.title}>{ticket.event.title}</Text>
        <Text style={styles.meta}>{formatDate(ticket.event.start_at)}</Text>
        <Text style={styles.meta}>{ticket.venue.name ?? ticket.venue.address_summary ?? 'Venue TBA'}</Text>
        <Text style={styles.meta}>Ticket: {ticket.ticket_tier_name} • {ticket.ticket_code}</Text>
        <Text style={styles.meta}>Status: {ticket.display_status}</Text>

        {ticket.can_display_entry_code && qrDataUri ? (
          <View style={styles.qrWrap}>
            <Image source={{ uri: qrDataUri }} style={styles.qr} />
            <Text style={styles.helper}>Present this code at entry.</Text>
          </View>
        ) : (
          <Text style={styles.helper}>Entry code unavailable for this ticket.</Text>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { gap: theme.spacing.sm },
  title: { color: theme.colors.textPrimary, fontSize: theme.typography.heading, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary },
  qrWrap: { marginTop: theme.spacing.lg, alignItems: 'center', gap: theme.spacing.sm, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.lg },
  qr: { width: 220, height: 220, borderRadius: theme.radius.sm, backgroundColor: '#fff' },
  helper: { color: theme.colors.textSecondary, textAlign: 'center' },
  stateWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: theme.colors.error },
});
