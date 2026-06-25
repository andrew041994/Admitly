import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { CameraView, BarcodeScanningResult, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { useIsFocused } from '@react-navigation/native';

import { checkInTicketManually, scanTicket } from '../../api/tickets';
import { theme } from '../../theme';
import {
  formatCheckedInTime,
  mapScanErrorToResult,
  mapScanResponseToResult,
  ScanResult,
  ScanUiState,
  shouldIgnoreDuplicateScan,
} from '../../features/scanner/scanFeedback';

type ScannerScreenProps = {
  canAccessScanner: boolean;
  eventId: number;
  eventTitle: string;
  onBack: () => void;
};

const RESULT_COOLDOWN_MS = 1400;

export function ScannerScreen({ canAccessScanner, eventId, eventTitle, onBack }: ScannerScreenProps) {
  const isFocused = useIsFocused();
  const [permission, requestPermission] = useCameraPermissions();
  const [isProcessingScan, setIsProcessingScan] = useState(false);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [lastScanRawValue, setLastScanRawValue] = useState<string | null>(null);
  const [lastScanAt, setLastScanAt] = useState(0);
  const [torchEnabled, setTorchEnabled] = useState(false);
  const [feedbackFlash, setFeedbackFlash] = useState<'success' | 'error' | null>(null);
  const [isManualEntryOpen, setIsManualEntryOpen] = useState(false);
  const [manualDigits, setManualDigits] = useState('');
  const [isSubmittingManualCode, setIsSubmittingManualCode] = useState(false);
  const [manualResult, setManualResult] = useState<ScanResult | null>(null);
  const cooldownTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flashTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const screenState: ScanUiState = useMemo(() => {
    if (!permission) {
      return 'requesting_permission';
    }

    if (!permission.granted) {
      return 'permission_denied';
    }

    if (isProcessingScan) {
      return 'processing';
    }

    if (!lastResult) {
      return 'ready';
    }

    return lastResult.outcome === 'success' ? 'success' : 'error';
  }, [isProcessingScan, lastResult, permission]);

  const runFeedbackHaptics = useCallback(async (result: ScanResult) => {
    try {
      if (result.outcome === 'success') {
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else if (result.outcome === 'already_used' || result.outcome === 'wrong_event') {
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      } else {
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      }
    } catch {
      // haptics is optional; scanner should still work without it
    }
  }, []);


  useEffect(() => {
    return () => {
      if (cooldownTimeoutRef.current) {
        clearTimeout(cooldownTimeoutRef.current);
      }
      if (flashTimeoutRef.current) {
        clearTimeout(flashTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!lastResult) {
      return;
    }

    const flashType = lastResult.outcome === 'success' ? 'success' : 'error';
    setFeedbackFlash(flashType);

    if (flashTimeoutRef.current) {
      clearTimeout(flashTimeoutRef.current);
    }

    flashTimeoutRef.current = setTimeout(() => {
      setFeedbackFlash(null);
    }, 360);
  }, [lastResult]);

  const releaseScanLock = useCallback(() => {
    if (cooldownTimeoutRef.current) {
      clearTimeout(cooldownTimeoutRef.current);
      cooldownTimeoutRef.current = null;
    }

    cooldownTimeoutRef.current = setTimeout(() => {
      setIsProcessingScan(false);
    }, RESULT_COOLDOWN_MS);
  }, []);

  const onBarcodeScanned = useCallback(
    async ({ data }: BarcodeScanningResult) => {
      if (!isFocused || !canAccessScanner || isProcessingScan) {
        return;
      }

      const rawPayload = data?.trim();
      const now = Date.now();

      if (!rawPayload || shouldIgnoreDuplicateScan(rawPayload, lastScanRawValue, lastScanAt, now)) {
        return;
      }

      setIsProcessingScan(true);
      setLastScanRawValue(rawPayload);
      setLastScanAt(now);

      try {
        const response = await scanTicket(rawPayload, eventId);
        const result = mapScanResponseToResult(response);
        setLastResult(result);
        runFeedbackHaptics(result);
      } catch (error) {
        const result = mapScanErrorToResult(error);
        setLastResult(result);
        runFeedbackHaptics(result);

        if (__DEV__) {
          // eslint-disable-next-line no-console
          console.warn('[Scanner] scan error', error);
        }
      } finally {
        releaseScanLock();
      }
    },
    [canAccessScanner, eventId, isFocused, isProcessingScan, lastScanAt, lastScanRawValue, releaseScanLock, runFeedbackHaptics],
  );

  const manualLookupValue = `ADM-${manualDigits}`;
  const canSubmitManualCode = manualDigits.length === 6 && !isSubmittingManualCode;

  const onManualDigitsChange = useCallback((value: string) => {
    setManualDigits(value.replace(/\D/g, '').slice(0, 6));
    setManualResult(null);
  }, []);

  const onSubmitManualCode = useCallback(async () => {
    if (!canSubmitManualCode) {
      return;
    }

    setIsSubmittingManualCode(true);

    try {
      const response = await checkInTicketManually(manualLookupValue, eventId);
      const result = mapScanResponseToResult(response);
      setLastResult(result);
      setManualResult(result);
      runFeedbackHaptics(result);

      if (result.outcome === 'success') {
        setManualDigits('');
        setIsManualEntryOpen(false);
      }
    } catch (error) {
      const result = mapScanErrorToResult(error);
      setLastResult(result);
      setManualResult(result);
      runFeedbackHaptics(result);

      if (__DEV__) {
        // eslint-disable-next-line no-console
        console.warn('[Scanner] manual check-in error', error);
      }
    } finally {
      setIsSubmittingManualCode(false);
    }
  }, [canSubmitManualCode, eventId, manualLookupValue, runFeedbackHaptics]);

  const statusLabel =
    screenState === 'processing'
      ? 'Processing…'
      : screenState === 'success'
        ? 'Last scan: successful'
      : screenState === 'error'
          ? 'Last scan: failed'
          : 'Ready to scan';

  if (!canAccessScanner) {
    return (
      <View style={styles.deniedWrap}>
        <Text style={styles.deniedTitle}>Scanner Access Required</Text>
        <Text style={styles.deniedText}>You do not have access to scanner mode on this account.</Text>
        <Pressable style={styles.backButton} onPress={onBack}>
          <Text style={styles.backButtonText}>Go Back</Text>
        </Pressable>
      </View>
    );
  }

  if (!permission) {
    return (
      <View style={styles.centeredWrap}>
        <ActivityIndicator color={theme.colors.primary} />
        <Text style={styles.stateText}>Preparing camera permissions…</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.deniedWrap}>
        <Text style={styles.deniedTitle}>Camera Access Needed</Text>
        <Text style={styles.deniedText}>Scanner mode needs camera access to read ticket QR codes.</Text>
        <Pressable style={styles.backButton} onPress={requestPermission}>
          <Text style={styles.backButtonText}>Grant Camera Access</Text>
        </Pressable>
        <Pressable onPress={onBack}>
          <Text style={styles.secondaryActionText}>Back</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {isFocused ? (
        <CameraView
          style={StyleSheet.absoluteFillObject}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          onBarcodeScanned={onBarcodeScanned}
          enableTorch={torchEnabled}
        />
      ) : null}

      <View style={styles.overlay}>
        {feedbackFlash ? (
          <View
            pointerEvents="none"
            style={[styles.feedbackFlash, feedbackFlash === 'success' ? styles.flashSuccess : styles.flashError]}
          />
        ) : null}

        <View style={styles.topBar}>
          <Pressable onPress={onBack} style={styles.topActionButton}>
            <Text style={styles.topActionText}>Back</Text>
          </Pressable>
          <View>
            <Text style={styles.title}>Scan Tickets</Text>
            <Text style={styles.subtitle}>{eventTitle}</Text>
          </View>
          <Pressable onPress={() => setTorchEnabled((prev) => !prev)} style={styles.topActionButton}>
            <Text style={styles.topActionText}>{torchEnabled ? 'Turn Torch Off' : 'Turn Torch On'}</Text>
          </Pressable>
        </View>

        <View style={styles.scanFrameWrap}>
          <View style={styles.scanMask}>
            <View style={styles.maskTop} />
            <View style={styles.maskCenterRow}>
              <View style={styles.maskSide} />
              <View style={styles.scanFrame}>
                <View style={[styles.corner, styles.topLeft]} />
                <View style={[styles.corner, styles.topRight]} />
                <View style={[styles.corner, styles.bottomLeft]} />
                <View style={[styles.corner, styles.bottomRight]} />
              </View>
              <View style={styles.maskSide} />
            </View>
            <View style={styles.maskBottom} />
          </View>
        </View>

        <View style={styles.bottomPanel}>
          <View style={styles.statusPill}>
            <View
              style={[
                styles.statusDot,
                screenState === 'processing'
                  ? styles.dotProcessing
                  : screenState === 'success'
                    ? styles.dotSuccess
                    : screenState === 'error'
                      ? styles.dotError
                      : styles.dotReady,
              ]}
            />
            <Text style={styles.statusLabel}>{statusLabel}</Text>
          </View>

          {lastResult ? (
            <View style={[styles.resultCard, lastResult.outcome === 'success' ? styles.resultSuccess : styles.resultError]}>
              <Text style={styles.resultTitle}>{lastResult.title}</Text>
              <Text style={styles.resultMessage}>{lastResult.message}</Text>
              {lastResult.attendeeName ? <Text style={styles.resultMeta}>Name: {lastResult.attendeeName}</Text> : null}
              {lastResult.ticketType ? <Text style={styles.resultMeta}>Ticket: {lastResult.ticketType}</Text> : null}
              {lastResult.checkedInAt ? (
                <Text style={styles.resultMeta}>Checked in: {formatCheckedInTime(lastResult.checkedInAt)}</Text>
              ) : null}
              <Pressable
                onPress={() => {
                  setLastResult(null);
                  setIsProcessingScan(false);
                }}
                style={styles.scanAgainButton}
              >
                <Text style={styles.scanAgainText}>Scan Again</Text>
              </Pressable>
            </View>
          ) : (
            <Text style={styles.hintText}>Hold the ticket QR code inside the frame.</Text>
          )}

          <Pressable style={styles.manualEntryButton} onPress={() => { setManualResult(null); setIsManualEntryOpen(true); }}>
            <Text style={styles.manualEntryButtonText}>Enter code manually</Text>
          </Pressable>
        </View>

        <Modal visible={isManualEntryOpen} transparent animationType="slide" onRequestClose={() => setIsManualEntryOpen(false)}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.modalBackdrop}
          >
            <Pressable style={styles.modalScrim} onPress={() => setIsManualEntryOpen(false)} />
            <View style={styles.manualSheet}>
              <Text style={styles.manualTitle}>Manual check-in code</Text>
              <Text style={styles.manualHelper}>Enter the 6-digit code shown on the ticket.</Text>

              <View style={styles.manualCodeRow}>
                <View style={styles.manualPrefixBox}>
                  <Text style={styles.manualPrefixText}>ADM -</Text>
                </View>
                <TextInput
                  accessibilityLabel="6-digit ticket code"
                  autoFocus
                  keyboardType="number-pad"
                  maxLength={6}
                  onChangeText={onManualDigitsChange}
                  placeholder="123456"
                  placeholderTextColor={theme.colors.textSecondary}
                  style={styles.manualInput}
                  value={manualDigits}
                />
              </View>

              {manualResult && manualResult.outcome !== 'success' ? (
                <View style={styles.manualErrorBox}>
                  <Text style={styles.manualErrorTitle}>{manualResult.title}</Text>
                  <Text style={styles.manualErrorText}>{manualResult.message}</Text>
                </View>
              ) : null}

              <View style={styles.manualActions}>
                <Pressable
                  style={[styles.manualActionButton, styles.manualCancelButton]}
                  onPress={() => setIsManualEntryOpen(false)}
                  disabled={isSubmittingManualCode}
                >
                  <Text style={styles.manualCancelText}>Cancel</Text>
                </Pressable>
                <Pressable
                  style={[styles.manualActionButton, styles.manualSubmitButton, !canSubmitManualCode && styles.manualSubmitDisabled]}
                  onPress={onSubmitManualCode}
                  disabled={!canSubmitManualCode}
                >
                  <Text style={styles.manualSubmitText}>{isSubmittingManualCode ? 'Checking in…' : 'Check in'}</Text>
                </Pressable>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  overlay: {
    flex: 1,
    justifyContent: 'space-between',
  },
  feedbackFlash: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 2,
  },
  flashSuccess: {
    backgroundColor: 'rgba(47,168,106,0.16)',
  },
  flashError: {
    backgroundColor: 'rgba(214,69,69,0.18)',
  },
  topBar: {
    paddingTop: theme.spacing.xl + theme.spacing.lg,
    paddingHorizontal: theme.spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  topActionButton: {
    borderColor: theme.colors.primary,
    borderWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radius.md,
    backgroundColor: '#141108',
  },
  topActionText: {
    color: theme.colors.primary,
    fontWeight: '700',
  },
  title: {
    color: theme.colors.textPrimary,
    textAlign: 'center',
    fontSize: theme.typography.heading,
    fontWeight: '700',
  },
  subtitle: {
    color: theme.colors.textSecondary,
    textAlign: 'center',
    marginTop: 4,
  },
  scanFrameWrap: {
    flex: 1,
    justifyContent: 'center',
  },
  scanMask: {
    flex: 1,
  },
  maskTop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.62)',
  },
  maskCenterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  maskSide: {
    flex: 1,
    height: 280,
    backgroundColor: 'rgba(0,0,0,0.62)',
  },
  maskBottom: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.62)',
  },
  scanFrame: {
    width: 280,
    height: 280,
    borderColor: 'rgba(212,175,55,0.55)',
    borderWidth: 2,
    backgroundColor: 'transparent',
  },
  corner: {
    position: 'absolute',
    width: 44,
    height: 44,
    borderColor: theme.colors.primary,
  },
  topLeft: {
    top: -1,
    left: -1,
    borderTopWidth: 5,
    borderLeftWidth: 5,
  },
  topRight: {
    top: -1,
    right: -1,
    borderTopWidth: 5,
    borderRightWidth: 5,
  },
  bottomLeft: {
    bottom: -1,
    left: -1,
    borderBottomWidth: 5,
    borderLeftWidth: 5,
  },
  bottomRight: {
    bottom: -1,
    right: -1,
    borderBottomWidth: 5,
    borderRightWidth: 5,
  },
  bottomPanel: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderTopColor: 'rgba(212,175,55,0.4)',
    borderTopWidth: 1,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  statusPill: {
    alignSelf: 'flex-start',
    backgroundColor: '#171717',
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.xs,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  dotReady: { backgroundColor: theme.colors.primary },
  dotProcessing: { backgroundColor: '#F4D03F' },
  dotSuccess: { backgroundColor: '#2FA86A' },
  dotError: { backgroundColor: '#D64545' },
  statusLabel: {
    color: theme.colors.textPrimary,
    fontWeight: '600',
  },
  resultCard: {
    borderRadius: theme.radius.md,
    borderWidth: 1,
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  resultSuccess: {
    borderColor: '#2FA86A',
    backgroundColor: 'rgba(47,168,106,0.15)',
  },
  resultError: {
    borderColor: '#D64545',
    backgroundColor: 'rgba(214,69,69,0.16)',
  },
  resultTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '700',
  },
  resultMessage: {
    color: theme.colors.textPrimary,
    fontWeight: '600',
  },
  resultMeta: {
    color: '#EFE3B2',
    fontSize: theme.typography.label,
  },
  hintText: {
    color: theme.colors.textSecondary,
  },
  scanAgainButton: {
    alignSelf: 'flex-start',
    marginTop: theme.spacing.xs,
    borderColor: theme.colors.primary,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    backgroundColor: '#1A1609',
  },
  scanAgainText: {
    color: theme.colors.primary,
    fontWeight: '700',
  },

  manualEntryButton: {
    alignSelf: 'stretch',
    borderColor: theme.colors.primary,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    backgroundColor: '#1A1609',
    alignItems: 'center',
  },
  manualEntryButtonText: {
    color: theme.colors.primary,
    fontWeight: '800',
  },
  modalBackdrop: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.58)',
  },
  manualSheet: {
    backgroundColor: theme.colors.surface,
    borderTopLeftRadius: theme.radius.lg,
    borderTopRightRadius: theme.radius.lg,
    borderColor: theme.colors.border,
    borderWidth: 1,
    padding: theme.spacing.lg,
    gap: theme.spacing.md,
  },
  manualTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '800',
  },
  manualHelper: {
    color: theme.colors.textSecondary,
  },
  manualCodeRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    overflow: 'hidden',
    backgroundColor: theme.colors.background,
  },
  manualPrefixBox: {
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.md,
    backgroundColor: '#171717',
    borderRightColor: theme.colors.border,
    borderRightWidth: 1,
  },
  manualPrefixText: {
    color: theme.colors.textPrimary,
    fontWeight: '800',
    fontSize: 20,
  },
  manualInput: {
    flex: 1,
    color: theme.colors.textPrimary,
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: 3,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  manualErrorBox: {
    borderColor: '#D64545',
    borderWidth: 1,
    borderRadius: theme.radius.md,
    backgroundColor: 'rgba(214,69,69,0.14)',
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  manualErrorTitle: {
    color: theme.colors.textPrimary,
    fontWeight: '800',
  },
  manualErrorText: {
    color: theme.colors.textPrimary,
  },
  manualActions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  manualActionButton: {
    flex: 1,
    alignItems: 'center',
    borderRadius: theme.radius.md,
    paddingVertical: theme.spacing.sm,
  },
  manualCancelButton: {
    borderColor: theme.colors.border,
    borderWidth: 1,
    backgroundColor: theme.colors.background,
  },
  manualCancelText: {
    color: theme.colors.textPrimary,
    fontWeight: '700',
  },
  manualSubmitButton: {
    backgroundColor: theme.colors.primary,
  },
  manualSubmitDisabled: {
    opacity: 0.45,
  },
  manualSubmitText: {
    color: '#141108',
    fontWeight: '800',
  },
  deniedWrap: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.xl,
    gap: theme.spacing.sm,
  },
  deniedTitle: {
    color: theme.colors.textPrimary,
    fontWeight: '700',
    fontSize: theme.typography.heading,
    textAlign: 'center',
  },
  deniedText: {
    color: theme.colors.textSecondary,
    textAlign: 'center',
  },
  centeredWrap: {
    flex: 1,
    backgroundColor: theme.colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing.sm,
  },
  stateText: {
    color: theme.colors.textSecondary,
  },
  backButton: {
    borderColor: theme.colors.primary,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    marginTop: theme.spacing.sm,
    backgroundColor: '#1A1609',
  },
  backButtonText: {
    color: theme.colors.primary,
    fontWeight: '700',
  },
  secondaryActionText: {
    color: theme.colors.textSecondary,
    marginTop: theme.spacing.sm,
  },
});
