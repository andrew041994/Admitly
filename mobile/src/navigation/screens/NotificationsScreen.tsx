import { useCallback, useEffect, useRef, useState } from 'react';
import * as Location from 'expo-location';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';

import {
  getNotificationPreferences,
  InAppNotification,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  NotificationPreferences,
  updateNotificationPreferences,
} from '../../api/notifications';
import { ApiError } from '../../api/client';
import { Screen } from '../../components/Screen';
import { requestAndRegisterPushToken } from '../../features/notifications/pushRegistration';
import { theme } from '../../theme';

type Props = { onOpenNotification: (notification: InAppNotification) => void };

export function NotificationsScreen({ onOpenNotification }: Props) {
  const [items, setItems] = useState<InAppNotification[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pushMessage, setPushMessage] = useState<string | null>(null);
  const openingNotificationId = useRef<number | null>(null);

  const load = useCallback(async (refresh = false) => {
    refresh ? setRefreshing(true) : setLoading(true);
    try {
      const [notifications, currentPreferences] = await Promise.all([
        listNotifications(), getNotificationPreferences(),
      ]);
      setItems(notifications.items);
      setNextCursor(notifications.next_cursor);
      setPreferences(currentPreferences);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to load notifications.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const loadMore = async () => {
    if (!nextCursor || loadingMore || loading || refreshing) return;
    setLoadingMore(true);
    try {
      const page = await listNotifications(nextCursor);
      setItems((current) => {
        const known = new Set(current.map((item) => item.id));
        return [...current, ...page.items.filter((item) => !known.has(item.id))];
      });
      setNextCursor(page.next_cursor);
    } catch {
      // Keep the current page; pull-to-refresh remains the explicit retry path.
    } finally { setLoadingMore(false); }
  };

  const open = (item: InAppNotification) => {
    if (openingNotificationId.current !== null) return;
    openingNotificationId.current = item.id;
    if (!item.is_read) {
      setItems((current) => current.map((row) => row.id === item.id ? { ...row, is_read: true } : row));
      void markNotificationRead(item.id).catch(() => load(true));
    }
    onOpenNotification(item);
    setTimeout(() => { openingNotificationId.current = null; }, 750);
  };

  const markAll = async () => {
    if (saving) return;
    setSaving(true);
    setItems((current) => current.map((row) => ({ ...row, is_read: true })));
    try { await markAllNotificationsRead(); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to mark notifications read.'); await load(true); }
    finally { setSaving(false); }
  };

  const updatePreference = async (payload: Parameters<typeof updateNotificationPreferences>[0]) => {
    if (saving) return;
    setSaving(true);
    try { setPreferences(await updateNotificationPreferences(payload)); setError(null); }
    catch (err) { setError(err instanceof ApiError ? err.message : 'Unable to update notification settings.'); }
    finally { setSaving(false); }
  };

  const enablePush = async () => {
    if (saving) return;
    setSaving(true);
    setPushMessage(null);
    try {
      const enabled = await requestAndRegisterPushToken();
      setPushMessage(enabled ? 'Push notifications are enabled on this device.' : 'Permission was not granted. You can continue using the in-app inbox.');
    } catch {
      setPushMessage('Push registration is unavailable on this build or device. The in-app inbox still works.');
    } finally { setSaving(false); }
  };

  const enableNearby = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setPushMessage('Location permission was not granted. Nearby alerts remain off.');
        return;
      }
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setPreferences(await updateNotificationPreferences({
        location_discovery_enabled: true,
        nearby_events_push_enabled: true,
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      }));
      setPushMessage('Nearby event alerts are enabled for your saved location.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save your location.');
    } finally { setSaving(false); }
  };

  return (
    <Screen padded={false}>
      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={theme.colors.primary} />}
        onEndReached={() => void loadMore()}
        onEndReachedThreshold={0.4}
        ListFooterComponent={loadingMore ? <ActivityIndicator color={theme.colors.primary} /> : null}
        ListHeaderComponent={(
          <>
            <View style={styles.headingRow}>
              <Text style={styles.title}>Notifications</Text>
              {items.some((item) => !item.is_read) ? (
                <Pressable accessibilityRole="button" disabled={saving} onPress={() => void markAll()} style={styles.textButton}>
                  <Text style={styles.textButtonLabel}>Mark all read</Text>
                </Pressable>
              ) : null}
            </View>
            {error ? <View style={styles.errorCard}><Text style={styles.error}>{error}</Text><Pressable onPress={() => void load()}><Text style={styles.retry}>Try again</Text></Pressable></View> : null}
            <View style={styles.settingsCard}>
              <Text style={styles.settingsTitle}>Device alerts</Text>
              <Text style={styles.settingsBody}>Enable push alerts for tickets, transfers, and event reminders. Permission is optional.</Text>
              <Pressable disabled={saving} onPress={() => void enablePush()} style={styles.enableButton} accessibilityRole="button">
                <Text style={styles.enableButtonText}>Enable push notifications</Text>
              </Pressable>
              {preferences ? (
                <>
                  <PreferenceRow label="Ticket and transfer alerts" value={preferences.ticket_activity_push_enabled} disabled={saving} onChange={(value) => void updatePreference({ ticket_activity_push_enabled: value })} />
                  <PreferenceRow label="Event reminders" value={preferences.event_reminders_push_enabled} disabled={saving} onChange={(value) => void updatePreference({ event_reminders_push_enabled: value })} />
                  <PreferenceRow
                    label="Nearby events (20 km)"
                    value={preferences.nearby_events_push_enabled}
                    disabled={saving}
                    onChange={(value) => value ? void enableNearby() : void updatePreference({ location_discovery_enabled: false, nearby_events_push_enabled: false })}
                  />
                </>
              ) : null}
              {pushMessage ? <Text style={styles.settingsBody}>{pushMessage}</Text> : null}
            </View>
            <Text style={styles.sectionTitle}>Inbox</Text>
          </>
        )}
        ListEmptyComponent={loading ? <ActivityIndicator color={theme.colors.primary} /> : <View style={styles.empty}><Text style={styles.emptyTitle}>You’re all caught up</Text><Text style={styles.settingsBody}>Ticket, transfer, nearby-event, and reminder updates will appear here.</Text></View>}
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${item.is_read ? '' : 'Unread. '}${item.title}. ${item.body}`}
            onPress={() => open(item)}
            style={[styles.notificationCard, !item.is_read && styles.unreadCard]}
          >
            <View style={styles.notificationTitleRow}>
              {!item.is_read ? <View style={styles.unreadDot} /> : null}
              <Text style={styles.notificationTitle}>{item.title}</Text>
            </View>
            <Text style={styles.notificationBody}>{item.body}</Text>
            <Text style={styles.timestamp}>{new Date(item.created_at).toLocaleString()}</Text>
          </Pressable>
        )}
      />
    </Screen>
  );
}

function PreferenceRow({ label, value, disabled, onChange }: { label: string; value: boolean; disabled: boolean; onChange: (value: boolean) => void }) {
  return <View style={styles.preferenceRow}><Text style={styles.preferenceLabel}>{label}</Text><Switch accessibilityLabel={label} value={value} disabled={disabled} onValueChange={onChange} trackColor={{ true: theme.colors.primaryMuted }} /></View>;
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.lg, paddingBottom: theme.spacing.xl * 2, gap: theme.spacing.sm },
  headingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: theme.spacing.md },
  title: { color: theme.colors.textPrimary, fontSize: theme.typography.heading, fontWeight: '700' },
  textButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: theme.spacing.sm },
  textButtonLabel: { color: theme.colors.primary, fontWeight: '700' },
  settingsCard: { borderRadius: theme.radius.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface, padding: theme.spacing.md, gap: theme.spacing.sm, marginBottom: theme.spacing.md },
  settingsTitle: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: 17 },
  settingsBody: { color: theme.colors.textSecondary, lineHeight: 20 },
  enableButton: { minHeight: 44, borderRadius: theme.radius.sm, backgroundColor: theme.colors.primary, alignItems: 'center', justifyContent: 'center', paddingHorizontal: theme.spacing.md },
  enableButtonText: { color: '#050505', fontWeight: '700' },
  preferenceRow: { minHeight: 48, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: theme.spacing.md },
  preferenceLabel: { color: theme.colors.textPrimary, flex: 1 },
  sectionTitle: { color: theme.colors.textSecondary, fontWeight: '700', marginBottom: theme.spacing.xs },
  notificationCard: { borderRadius: theme.radius.md, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface, padding: theme.spacing.md, gap: theme.spacing.xs, minHeight: 96 },
  unreadCard: { borderColor: theme.colors.primaryMuted, backgroundColor: theme.colors.surfaceElevated },
  notificationTitleRow: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.xs },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: theme.colors.primary },
  notificationTitle: { color: theme.colors.textPrimary, fontWeight: '700', flex: 1 },
  notificationBody: { color: theme.colors.textSecondary, lineHeight: 20 },
  timestamp: { color: theme.colors.textSecondary, fontSize: theme.typography.caption },
  empty: { alignItems: 'center', paddingVertical: theme.spacing.xl, gap: theme.spacing.sm },
  emptyTitle: { color: theme.colors.textPrimary, fontWeight: '700', fontSize: 18 },
  errorCard: { borderColor: theme.colors.error, borderWidth: 1, borderRadius: theme.radius.sm, padding: theme.spacing.md, marginBottom: theme.spacing.md },
  error: { color: theme.colors.error },
  retry: { color: theme.colors.primary, marginTop: theme.spacing.sm, fontWeight: '700' },
});
