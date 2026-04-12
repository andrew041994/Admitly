import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { CameraView, BarcodeScanningResult, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { useIsFocused } from '@react-navigation/native';

import { scanTicket } from '../../api/tickets';
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
  const cooldownTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    };
  }, []);

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

  const statusLabel =
    screenState === 'processing'
      ? 'Processing…'
      : screenState === 'success'
        ? 'Last scan: success'
        : screenState === 'error'
          ? 'Last scan: issue detected'
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
        <View style={styles.topBar}>
          <Pressable onPress={onBack} style={styles.topActionButton}>
            <Text style={styles.topActionText}>Back</Text>
          </Pressable>
          <View>
            <Text style={styles.title}>Scan Tickets</Text>
            <Text style={styles.subtitle}>{eventTitle}</Text>
          </View>
          <Pressable onPress={() => setTorchEnabled((prev) => !prev)} style={styles.topActionButton}>
            <Text style={styles.topActionText}>{torchEnabled ? 'Torch On' : 'Torch Off'}</Text>
          </Pressable>
        </View>

        <View style={styles.scanFrameWrap}>
          <View style={styles.scanFrame}>
            <View style={[styles.corner, styles.topLeft]} />
            <View style={[styles.corner, styles.topRight]} />
            <View style={[styles.corner, styles.bottomLeft]} />
            <View style={[styles.corner, styles.bottomRight]} />
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
            <Text style={styles.hintText}>Point your camera at a ticket QR code.</Text>
          )}

          {/* TODO(phase-8): add manual code entry fallback when manual check-in endpoint is finalized. */}
        </View>
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
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'space-between',
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
    alignItems: 'center',
    justifyContent: 'center',
  },
  scanFrame: {
    width: 260,
    height: 260,
    borderColor: 'rgba(212,175,55,0.25)',
    borderWidth: 1,
    backgroundColor: 'rgba(5,5,5,0.1)',
  },
  corner: {
    position: 'absolute',
    width: 34,
    height: 34,
    borderColor: theme.colors.primary,
  },
  topLeft: {
    top: -1,
    left: -1,
    borderTopWidth: 4,
    borderLeftWidth: 4,
  },
  topRight: {
    top: -1,
    right: -1,
    borderTopWidth: 4,
    borderRightWidth: 4,
  },
  bottomLeft: {
    bottom: -1,
    left: -1,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
  },
  bottomRight: {
    bottom: -1,
    right: -1,
    borderBottomWidth: 4,
    borderRightWidth: 4,
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
