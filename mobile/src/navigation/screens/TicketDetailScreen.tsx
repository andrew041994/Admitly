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

function formatManualCode(code: string): string {
  const digits = code.replace(/^ADM-/i, '');
  return `ADM - ${digits}`;
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
        <Text style={styles.meta}>Ticket: {ticket.ticket_tier_name}</Text>
        <View style={styles.manualCodeWrap}>
          <Text style={styles.manualCodeLabel}>Check-in Code</Text>
          <Text style={styles.manualCode}>{ticket.manual_code_display || formatManualCode(ticket.manual_code)}</Text>
        </View>
        <Text style={styles.meta}>Status: {ticket.display_status}</Text>

        {ticket.can_display_entry_code && qrDataUri ? (
          <View style={styles.qrWrap}>
            <Image source={{ uri: qrDataUri }} style={styles.qr} />
            <Text style={styles.helper}>Present this QR code at entry. Scanner not working? Give staff your check-in code.</Text>
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
  manualCodeWrap: { marginVertical: theme.spacing.md, alignItems: 'center', gap: theme.spacing.xs, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.lg },
  manualCodeLabel: { color: theme.colors.textSecondary, fontSize: 14, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  manualCode: { color: theme.colors.textPrimary, fontSize: 30, fontWeight: '800', letterSpacing: 1.2 },
  qrWrap: { marginTop: theme.spacing.lg, alignItems: 'center', gap: theme.spacing.sm, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.lg },
  qr: { width: 220, height: 220, borderRadius: theme.radius.sm, backgroundColor: '#fff' },
  helper: { color: theme.colors.textSecondary, textAlign: 'center' },
  stateWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: theme.colors.error },
});
