import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../api/client';
import {
  TicketTransferRecipientResolution,
  WalletTicketDetail,
  createTicketTransfer,
  getMyTicket,
  getMyTicketQr,
  listMyTicketTransfers,
  resolveTicketTransferRecipient,
} from '../../api/tickets';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { canCreateResolvedTransfer, canSubmitTransfer, normalizeTransferEmail } from '../../features/transfers/validation';
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


function statusLabel(status: WalletTicketDetail['display_status']): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function TicketDetailScreen({ ticketId }: TicketDetailScreenProps) {
  const [ticket, setTicket] = useState<WalletTicketDetail | null>(null);
  const [qrDataUri, setQrDataUri] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [transferError, setTransferError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [resolution, setResolution] = useState<TicketTransferRecipientResolution | null>(null);
  const [resolving, setResolving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [transferMessage, setTransferMessage] = useState<string | null>(null);

  async function refreshTicket() {
    const refreshed = await getMyTicket(ticketId);
    setTicket(refreshed);
    if (!refreshed.can_display_entry_code) setQrDataUri(null);
  }

  useEffect(() => {
    getMyTicket(ticketId)
      .then(async (ticketData) => {
        setTicket(ticketData);
        if (ticketData.can_display_entry_code) {
          const qrData = await getMyTicketQr(ticketId);
          setQrDataUri(qrData.qr_data_uri);
        }
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Unable to load ticket.'));
  }, [ticketId]);

  const normalizedEmail = normalizeTransferEmail(email);

  async function continueToConfirmation() {
    if (!canSubmitTransfer(normalizedEmail, resolving) || !normalizedEmail) return;
    setResolving(true);
    setTransferError(null);
    setTransferMessage(null);
    try {
      setResolution(await resolveTicketTransferRecipient(ticketId, normalizedEmail));
    } catch (err) {
      setResolution(null);
      setTransferError(err instanceof ApiError ? err.message : 'Unable to confirm the recipient. Check your connection and try again.');
    } finally {
      setResolving(false);
    }
  }

  async function submitTransfer() {
    if (!resolution || !canCreateResolvedTransfer(resolution.recipient_resolution_reference, submitting)) return;
    if (new Date(resolution.resolution_expires_at).getTime() <= Date.now()) {
      setResolution(null);
      setTransferError('Recipient confirmation expired. Look up the recipient again.');
      return;
    }
    setSubmitting(true);
    setTransferError(null);
    try {
      const created = await createTicketTransfer(ticketId, resolution.recipient_resolution_reference);
      if (created.status !== 'pending') throw new Error('The transfer was not created.');
      setTransferMessage('Transfer invitation created. The recipient will receive the ticket after accepting.');
      setResolution(null);
      setEmail('');
      await refreshTicket();
    } catch (err) {
      if (err instanceof ApiError && err.status === 410) {
        setResolution(null);
        setTransferError('Recipient confirmation expired. Look up the recipient again.');
      } else if (!(err instanceof ApiError)) {
        try {
          const outgoing = await listMyTicketTransfers('outgoing');
          const committed = outgoing.some((item) => item.ticket_id === ticketId && item.status === 'pending');
          if (committed) {
            setTransferMessage('Transfer invitation created. The recipient will receive the ticket after accepting.');
            setResolution(null);
            setEmail('');
            await refreshTicket();
          } else {
            setTransferError('Unable to confirm whether the transfer was created. Check your connection and try again.');
          }
        } catch {
          setTransferError('Unable to confirm whether the transfer was created. Refresh your transfers before trying again.');
        }
      } else {
        setTransferError(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) return <Screen><View style={styles.stateWrap}><Text style={styles.error}>{loadError}</Text></View></Screen>;
  if (!ticket) return <Screen><View style={styles.stateWrap}><ActivityIndicator color={theme.colors.primary} /></View></Screen>;

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={styles.container}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>{ticket.event.title}</Text>
        <Text style={styles.meta}>{formatDate(ticket.event.start_at)}</Text>
        <Text style={styles.meta}>{ticket.venue.name ?? ticket.venue.address_summary ?? 'Venue TBA'}</Text>
        <Text style={styles.meta}>Ticket: {ticket.ticket_tier_name}</Text>
        {ticket.can_display_entry_code ? (
          <View style={styles.manualCodeWrap}>
            <Text style={styles.manualCodeLabel}>Check-in Code</Text>
            <Text style={styles.manualCode}>{ticket.manual_code_display || formatManualCode(ticket.manual_code)}</Text>
          </View>
        ) : null}
        <Text accessibilityLabel={`Ticket status: ${statusLabel(ticket.display_status)}`} style={[styles.status, styles[`status_${ticket.display_status}`]]}>Status: {statusLabel(ticket.display_status)}</Text>

        {ticket.can_display_entry_code && qrDataUri ? (
          <View style={styles.qrWrap}>
            <Image source={{ uri: qrDataUri }} style={styles.qr} />
            <Text style={styles.helper}>Present this QR code at entry. Scanner not working? Give staff your check-in code.</Text>
          </View>
        ) : (
          <Text style={styles.helper}>Entry code unavailable for this ticket.</Text>
        )}

        <View style={styles.transferCard}>
          <Text style={styles.transferTitle}>Transfer ticket</Text>
          {!ticket.can_transfer ? (
            <Text style={styles.helper}>{ticket.transfer_unavailable_reason ?? 'This ticket cannot be transferred.'}</Text>
          ) : resolution ? (
            <View style={styles.formGap}>
              <Text style={styles.confirmTitle}>Confirm recipient</Text>
              <Text style={styles.helperLeft}>You’re transferring this ticket to:</Text>
              <Text style={styles.recipientName}>{resolution.recipient_display_name}</Text>
              <Text style={styles.recipientEmail}>{resolution.recipient_email}</Text>
              <Text style={styles.meta}>{ticket.event.title}</Text>
              <Text style={styles.meta}>{ticket.ticket_tier_name}</Text>
              <Text style={styles.meta}>{formatDate(ticket.event.start_at)}</Text>
              <Text style={styles.warning}>Ownership moves only after the recipient accepts. Until then, the ticket remains yours and cannot be checked in.</Text>
              <Text style={styles.confirmTitle}>Is this the correct recipient?</Text>
              <ThemedButton label="Transfer ticket" onPress={submitTransfer} loading={submitting} disabled={submitting} />
              <ThemedButton label="Cancel" variant="secondary" onPress={() => setResolution(null)} disabled={submitting} />
            </View>
          ) : (
            <View style={styles.formGap}>
              <Text style={styles.modeLabel}>Email transfer</Text>
              <TextInput
                accessibilityLabel="Recipient email"
                value={email}
                onChangeText={(value) => { setEmail(value); setTransferError(null); }}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                placeholder="recipient@example.com"
                placeholderTextColor={theme.colors.textSecondary}
                style={styles.input}
              />
              {email && !normalizedEmail ? <Text style={styles.error}>Enter a valid email address.</Text> : null}
              <ThemedButton label="Continue" onPress={continueToConfirmation} loading={resolving} disabled={!canSubmitTransfer(normalizedEmail, resolving)} />
            </View>
          )}
          {transferError ? <Text accessibilityRole="alert" style={styles.error}>{transferError}</Text> : null}
          {transferMessage ? <Text style={styles.success}>{transferMessage}</Text> : null}
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: { gap: theme.spacing.sm, paddingBottom: theme.spacing.xl },
  title: { color: theme.colors.textPrimary, fontSize: theme.typography.heading, fontWeight: '700' },
  meta: { color: theme.colors.textSecondary },
  status: { fontWeight: '700', paddingVertical: theme.spacing.xs },
  status_active: { color: '#98e067' },
  status_used: { color: '#8fd5ff' },
  status_expired: { color: theme.colors.textSecondary },
  status_refunded: { color: '#ffc46b' },
  manualCodeWrap: { marginVertical: theme.spacing.md, alignItems: 'center', gap: theme.spacing.xs, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.lg },
  manualCodeLabel: { color: theme.colors.textSecondary, fontSize: 14, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  manualCode: { color: theme.colors.textPrimary, fontSize: 30, fontWeight: '800', letterSpacing: 1.2 },
  qrWrap: { marginTop: theme.spacing.lg, alignItems: 'center', gap: theme.spacing.sm, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.lg },
  qr: { width: 220, height: 220, borderRadius: theme.radius.sm, backgroundColor: '#fff' },
  helper: { color: theme.colors.textSecondary, textAlign: 'center' },
  helperLeft: { color: theme.colors.textSecondary },
  stateWrap: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: theme.colors.error },
  success: { color: '#98e067', textAlign: 'center' },
  transferCard: { marginTop: theme.spacing.lg, gap: theme.spacing.sm, backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.md },
  transferTitle: { color: theme.colors.textPrimary, fontSize: 18, fontWeight: '700' },
  confirmTitle: { color: theme.colors.textPrimary, fontWeight: '700' },
  recipientName: { color: theme.colors.textPrimary, fontSize: 18, fontWeight: '700' },
  recipientEmail: { color: theme.colors.primary },
  warning: { color: theme.colors.textSecondary, paddingVertical: theme.spacing.sm },
  formGap: { gap: theme.spacing.sm },
  modeLabel: { color: theme.colors.textPrimary, fontWeight: '600' },
  input: { color: theme.colors.textPrimary, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.sm, paddingHorizontal: theme.spacing.sm, paddingVertical: 12 },
});
