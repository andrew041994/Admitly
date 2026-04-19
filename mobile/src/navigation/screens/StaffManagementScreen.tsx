import { useEffect, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../api/client';
import { assignCheckinStaff, listEventStaff, listMyActiveEvents, removeEventStaff, searchUsers } from '../../api/organizer';
import { theme } from '../../theme';

export function StaffManagementScreen() {
  const getStaffLabel = (row: { user_id: number; username: string | null; display_name: string | null; full_name: string | null; email: string | null }) => {
    const resolved = row.username ?? row.display_name ?? row.full_name ?? row.email;
    return resolved && resolved.trim().length > 0 ? resolved : `User #${row.user_id}`;
  };
  const [eventId, setEventId] = useState<number | null>(null);
  const [events, setEvents] = useState<Array<{ id: number; title: string }>>([]);
  const [staff, setStaff] = useState<Array<{ id: number; user_id: number; username: string | null; display_name: string | null; full_name: string | null; email: string | null; is_effective_active: boolean }>>([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Array<{ id: number; full_name: string }>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMyActiveEvents()
      .then((rows) => {
        setEvents(rows.map((row) => ({ id: row.id, title: row.title })));
        if (rows[0]) setEventId(rows[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load active events.'));
  }, []);

  useEffect(() => {
    if (!eventId) return;
    listEventStaff(eventId).then(setStaff).catch(() => undefined);
  }, [eventId]);

  const onSearch = async () => {
    if (query.trim().length < 2) return;
    try {
      const users = await searchUsers(query.trim());
      setResults(users.map((row) => ({ id: row.id, full_name: row.full_name })));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Search failed.');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Staff Management</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Text style={styles.section}>Select active event</Text>
      <View style={styles.row}>
        {events.map((event) => (
          <Pressable key={event.id} onPress={() => setEventId(event.id)} style={[styles.pill, eventId === event.id && styles.pillActive]}>
            <Text style={[styles.pillText, eventId === event.id && styles.pillTextActive]}>{event.title}</Text>
          </Pressable>
        ))}
      </View>

      <TextInput style={styles.input} value={query} onChangeText={setQuery} placeholder="Search name/email/phone" placeholderTextColor={theme.colors.textSecondary} />
      <Pressable style={styles.button} onPress={onSearch}><Text style={styles.buttonText}>Search users</Text></Pressable>
      <FlatList
        style={styles.searchResults}
        data={results}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <Pressable
            style={styles.item}
            onPress={async () => {
              if (!eventId) return;
              await assignCheckinStaff(eventId, item.id);
              setStaff(await listEventStaff(eventId));
            }}
          >
            <Text style={styles.itemTitle}>{item.full_name}</Text>
            <Text style={styles.meta}>Tap to assign</Text>
          </Pressable>
        )}
      />

      <Text style={styles.section}>Assigned staff</Text>
      {staff.map((row) => (
        <View key={row.id} style={styles.staffRow}>
          <Text style={styles.meta}>{getStaffLabel(row)} • {row.is_effective_active ? 'Active' : 'Expired'}</Text>
          {eventId ? <Pressable onPress={async () => { await removeEventStaff(eventId, row.id); setStaff(await listEventStaff(eventId)); }}><Text style={styles.remove}>Remove</Text></Pressable> : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background, padding: theme.spacing.lg },
  title: { color: theme.colors.textPrimary, fontSize: 22, fontWeight: '700', marginBottom: theme.spacing.sm },
  section: { color: theme.colors.textSecondary, marginVertical: theme.spacing.sm },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.xs },
  pill: { borderWidth: 1, borderColor: theme.colors.border, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  pillActive: { borderColor: theme.colors.primary },
  pillText: { color: theme.colors.textSecondary },
  pillTextActive: { color: theme.colors.primary, fontWeight: '700' },
  input: { borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, padding: theme.spacing.sm, color: theme.colors.textPrimary, backgroundColor: theme.colors.surface },
  button: { backgroundColor: theme.colors.surface, borderWidth: 1, borderColor: theme.colors.border, padding: theme.spacing.sm, borderRadius: theme.radius.md, marginTop: theme.spacing.xs, marginBottom: theme.spacing.sm },
  buttonText: { color: theme.colors.textPrimary, fontWeight: '600' },
  item: { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, borderWidth: 1, borderRadius: theme.radius.md, padding: theme.spacing.sm, marginBottom: theme.spacing.xs },
  searchResults: { flexGrow: 0, maxHeight: 220, marginBottom: theme.spacing.xs },
  itemTitle: { color: theme.colors.textPrimary, fontWeight: '600' },
  meta: { color: theme.colors.textSecondary },
  staffRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  remove: { color: theme.colors.error },
  error: { color: theme.colors.error },
});
