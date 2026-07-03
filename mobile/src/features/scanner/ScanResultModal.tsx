import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { theme } from '../../theme';
import { formatCheckedInTime, getScanResultTone, ScanResult } from './scanFeedback';

type ScanResultModalProps = {
  visible: boolean;
  result: ScanResult | null;
  onScanNext: () => void;
  onSecondaryAction?: () => void;
  secondaryActionLabel?: string;
};

export function ScanResultModal({
  visible,
  result,
  onScanNext,
  onSecondaryAction,
  secondaryActionLabel,
}: ScanResultModalProps) {
  const insets = useSafeAreaInsets();

  if (!result) {
    return null;
  }

  const tone = getScanResultTone(result);
  const toneStyle = tone === 'success' ? styles.success : tone === 'warning' ? styles.warning : tone === 'unable' ? styles.unable : styles.error;
  const statusLabel = tone === 'success' ? 'Success' : tone === 'warning' ? 'Warning' : tone === 'unable' ? 'Unable to Scan' : 'Failed';

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onScanNext}>
      <View style={[styles.backdrop, { paddingTop: insets.top + theme.spacing.md, paddingBottom: insets.bottom + theme.spacing.md }]}>
        <View style={[styles.card, toneStyle]}>
          <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false} bounces={false}>
            <View style={[styles.statusPill, toneStyle]}>
              <Text style={styles.statusText}>{statusLabel}</Text>
            </View>
            <Text style={styles.title}>{result.title}</Text>
            <Text style={styles.message}>{result.message}</Text>

            <View style={styles.detailsBox}>
              <Text style={styles.detailsTitle}>Scan outcome</Text>
              <Text style={styles.detailText}>{result.outcome.replace(/_/g, ' ')}</Text>
              {result.eventTitle ? <Text style={styles.detailText}>Event: {result.eventTitle}</Text> : null}
              {result.attendeeName ? <Text style={styles.detailText}>Name: {result.attendeeName}</Text> : null}
              {result.ticketType ? <Text style={styles.detailText}>Ticket: {result.ticketType}</Text> : null}
              {result.checkedInAt ? <Text style={styles.detailText}>Checked in: {formatCheckedInTime(result.checkedInAt)}</Text> : null}
            </View>
          </ScrollView>

          <View style={styles.actions}>
            {secondaryActionLabel && onSecondaryAction ? (
              <Pressable style={[styles.actionButton, styles.secondaryButton]} onPress={onSecondaryAction}>
                <Text style={styles.secondaryText}>{secondaryActionLabel}</Text>
              </Pressable>
            ) : null}
            <Pressable style={[styles.actionButton, styles.primaryButton]} onPress={onScanNext}>
              <Text style={styles.primaryText}>Scan Next</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.md,
    backgroundColor: 'rgba(0,0,0,0.72)',
  },
  card: {
    maxHeight: '88%',
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    backgroundColor: theme.colors.surface,
    overflow: 'hidden',
  },
  content: {
    padding: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  success: { borderColor: theme.colors.success },
  warning: { borderColor: '#F4D03F' },
  error: { borderColor: theme.colors.error },
  unable: { borderColor: theme.colors.primary },
  statusPill: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    backgroundColor: theme.colors.surfaceElevated,
  },
  statusText: {
    color: theme.colors.textPrimary,
    fontWeight: '800',
    textTransform: 'uppercase',
    fontSize: theme.typography.caption,
    letterSpacing: 0.8,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '800',
  },
  message: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.body,
    lineHeight: 23,
  },
  detailsBox: {
    marginTop: theme.spacing.xs,
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
    backgroundColor: theme.colors.background,
  },
  detailsTitle: {
    color: theme.colors.textSecondary,
    fontWeight: '800',
    textTransform: 'uppercase',
    fontSize: theme.typography.caption,
  },
  detailText: {
    color: '#EFE3B2',
    fontSize: theme.typography.label,
    textTransform: 'capitalize',
  },
  actions: {
    padding: theme.spacing.lg,
    paddingTop: 0,
    gap: theme.spacing.sm,
  },
  actionButton: {
    alignItems: 'center',
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.sm,
  },
  primaryButton: { backgroundColor: theme.colors.primary },
  primaryText: { color: '#141108', fontWeight: '900' },
  secondaryButton: {
    borderColor: theme.colors.border,
    borderWidth: 1,
    backgroundColor: theme.colors.background,
  },
  secondaryText: { color: theme.colors.textPrimary, fontWeight: '800' },
});
