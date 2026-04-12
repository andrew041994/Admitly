import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiError } from '../../api/client';
import { DiscoveryFilters, EventDiscoveryItem, listDiscoverableEvents } from '../../api/events';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { EventCard } from '../components/EventCard';
import { theme } from '../../theme';

type DateFilter = 'today' | 'this_week' | 'upcoming';

type HomeScreenProps = {
  onOpenProfile: () => void;
  onOpenMyTickets: () => void;
  onSignOut: () => void;
  onOpenEvent: (eventId: number) => void;
};

const CATEGORY_FILTERS = ['All', 'Party', 'Concert', 'Festival'];

export function HomeScreen({ onOpenProfile, onOpenMyTickets, onSignOut, onOpenEvent }: HomeScreenProps) {
  const [events, setEvents] = useState<EventDiscoveryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [dateFilter, setDateFilter] = useState<DateFilter>('upcoming');
  const [priceFilter, setPriceFilter] = useState<'all' | 'free' | 'paid'>('all');

  useEffect(() => {
    const timeout = setTimeout(() => setQuery(searchInput.trim()), 300);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const requestFilters = useMemo<DiscoveryFilters>(() => {
    const isFree = priceFilter === 'all' ? undefined : priceFilter === 'free';
    return {
      query,
      dateBucket: dateFilter,
      category: selectedCategory === 'All' ? undefined : selectedCategory,
      isFree,
    };
  }, [dateFilter, priceFilter, query, selectedCategory]);

  const loadEvents = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const discoveredEvents = await listDiscoverableEvents(requestFilters);
        setEvents(discoveredEvents);
        setError(null);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Unable to load events right now.';
        setError(message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [requestFilters],
  );

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  return (
    <Screen padded={false}>
      <View style={styles.container}>
        <View style={styles.header}>
          <View>
            <Text style={styles.kicker}>DISCOVER</Text>
            <Text style={styles.title}>Admitly</Text>
          </View>
          <View style={styles.headerLinks}>
            <Pressable onPress={onOpenMyTickets}><Text style={styles.profileLink}>My Tickets</Text></Pressable>
            <Pressable onPress={onOpenProfile}><Text style={styles.profileLink}>Profile</Text></Pressable>
          </View>
        </View>

        <View style={styles.searchWrap}>
          <TextInput
            value={searchInput}
            onChangeText={setSearchInput}
            placeholder="Search events, venues, vibes"
            placeholderTextColor={theme.colors.textSecondary}
            style={styles.searchInput}
            returnKeyType="search"
          />
        </View>

        <View style={styles.filtersRow}>
          {CATEGORY_FILTERS.map((item) => (
            <Pressable
              key={item}
              style={[styles.chip, selectedCategory === item && styles.chipActive]}
              onPress={() => setSelectedCategory(item)}
            >
              <Text style={[styles.chipText, selectedCategory === item && styles.chipTextActive]}>{item}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.filtersRow}>
          {[
            { key: 'today', label: 'Today' },
            { key: 'this_week', label: 'This Week' },
            { key: 'upcoming', label: 'Upcoming' },
          ].map((item) => (
            <Pressable
              key={item.key}
              style={[styles.chip, dateFilter === item.key && styles.chipActive]}
              onPress={() => setDateFilter(item.key as DateFilter)}
            >
              <Text style={[styles.chipText, dateFilter === item.key && styles.chipTextActive]}>{item.label}</Text>
            </Pressable>
          ))}
          {[
            { key: 'all', label: 'All' },
            { key: 'free', label: 'Free' },
            { key: 'paid', label: 'Paid' },
          ].map((item) => (
            <Pressable
              key={item.key}
              style={[styles.chip, priceFilter === item.key && styles.chipActive]}
              onPress={() => setPriceFilter(item.key as 'all' | 'free' | 'paid')}
            >
              <Text style={[styles.chipText, priceFilter === item.key && styles.chipTextActive]}>{item.label}</Text>
            </Pressable>
          ))}
        </View>

        {loading ? (
          <View style={styles.stateWrap}>
            <ActivityIndicator color={theme.colors.primary} />
            <Text style={styles.stateText}>Loading events...</Text>
          </View>
        ) : error ? (
          <View style={styles.stateWrap}>
            <Text style={styles.errorText}>{error}</Text>
            <ThemedButton label="Try Again" onPress={() => loadEvents()} variant="secondary" />
          </View>
        ) : events.length === 0 ? (
          <View style={styles.stateWrap}>
            <Text style={styles.stateText}>No events match your current search and filters.</Text>
          </View>
        ) : (
          <FlatList
            data={events}
            keyExtractor={(item) => String(item.id)}
            contentContainerStyle={styles.listContent}
            renderItem={({ item }) => <EventCard event={item} onPress={() => onOpenEvent(item.id)} />}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={() => loadEvents(true)}
                tintColor={theme.colors.primary}
              />
            }
          />
        )}

        <Pressable onPress={onSignOut} style={styles.signOutArea}>
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: theme.spacing.md,
  },
  header: {
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  kicker: {
    color: theme.colors.primary,
    fontSize: theme.typography.caption,
    letterSpacing: 2,
  },
  title: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.heading,
    fontWeight: '700',
  },
  headerLinks: { flexDirection: 'row', gap: theme.spacing.md },
  profileLink: { color: theme.colors.primary, fontWeight: '600' },
  searchWrap: {
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  searchInput: {
    borderColor: theme.colors.border,
    borderWidth: 1,
    borderRadius: theme.radius.md,
    backgroundColor: theme.colors.surface,
    color: theme.colors.textPrimary,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  filtersRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
  },
  chipActive: {
    borderColor: theme.colors.primary,
    backgroundColor: '#221b08',
  },
  chipText: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.caption,
  },
  chipTextActive: {
    color: theme.colors.primary,
    fontWeight: '700',
  },
  listContent: {
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
    paddingBottom: theme.spacing.xl,
  },
  stateWrap: {
    paddingHorizontal: theme.spacing.lg,
    alignItems: 'center',
    gap: theme.spacing.md,
    marginTop: theme.spacing.xl,
  },
  stateText: {
    color: theme.colors.textSecondary,
    textAlign: 'center',
  },
  errorText: {
    color: theme.colors.error,
    textAlign: 'center',
  },
  signOutArea: {
    paddingVertical: theme.spacing.sm,
    alignItems: 'center',
  },
  signOutText: {
    color: theme.colors.textSecondary,
  },
});
