import { useCallback, useEffect, useMemo, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import {
  ActivityIndicator,
  FlatList,
  LayoutAnimation,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  UIManager,
  View,
} from 'react-native';

import { ApiError } from '../../api/client';
import { getUnreadNotificationCount } from '../../api/notifications';
import { DiscoveryFilters, EventDiscoveryDetail, EventDiscoveryItem, getDiscoverableEventDetail, listDiscoverableEvents } from '../../api/events';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { EventCard } from '../components/EventCard';
import { theme } from '../../theme';

type DateFilter = 'today' | 'this_week' | 'upcoming';

type HomeScreenProps = {
  onOpenProfile: () => void;
  onOpenMyTickets: () => void;
  onOpenNotifications: () => void;
  onSignOut: () => void;
  onOpenEvent: (eventId: number) => void;
  onGetTickets: (eventId: number) => void;
};

const CATEGORY_FILTERS = ['All', 'Party', 'Concert', 'Festival'];

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export function HomeScreen({ onOpenProfile, onOpenMyTickets, onOpenNotifications, onSignOut, onOpenEvent, onGetTickets }: HomeScreenProps) {
  const [events, setEvents] = useState<EventDiscoveryItem[]>([]);
  const [featuredEvents, setFeaturedEvents] = useState<EventDiscoveryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [dateFilter, setDateFilter] = useState<DateFilter>('upcoming');
  const [priceFilter, setPriceFilter] = useState<'all' | 'free' | 'paid'>('all');
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null);
  const [eventDetailsById, setEventDetailsById] = useState<Record<number, EventDiscoveryDetail>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null);
  const [detailErrorById, setDetailErrorById] = useState<Record<number, string | null>>({});
  const [unreadCount, setUnreadCount] = useState(0);

  const refreshUnreadCount = useCallback(async () => {
    try { setUnreadCount((await getUnreadNotificationCount()).unread_count); } catch { /* inbox remains available offline */ }
  }, []);

  useFocusEffect(useCallback(() => {
    void refreshUnreadCount();
    const interval = setInterval(() => void refreshUnreadCount(), 30000);
    return () => clearInterval(interval);
  }, [refreshUnreadCount]));

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

  const featuredSubset = useMemo(() => featuredEvents.slice(0, 6), [featuredEvents]);
  const hasActiveFilters = Boolean(query || selectedCategory !== 'All' || dateFilter !== 'upcoming' || priceFilter !== 'all');

  const resetFilters = useCallback(() => {
    setSearchInput('');
    setQuery('');
    setSelectedCategory('All');
    setDateFilter('upcoming');
    setPriceFilter('all');
    setExpandedEventId(null);
  }, []);

  useEffect(() => {
    setExpandedEventId(null);
  }, [requestFilters]);

  const toggleEventExpansion = useCallback(
    async (eventId: number) => {
      LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
      if (expandedEventId === eventId) {
        setExpandedEventId(null);
        return;
      }

      setExpandedEventId(eventId);
      if (eventDetailsById[eventId]) return;

      setDetailLoadingId(eventId);
      setDetailErrorById((current) => ({ ...current, [eventId]: null }));
      try {
        const eventDetail = await getDiscoverableEventDetail(eventId);
        setEventDetailsById((current) => ({ ...current, [eventId]: eventDetail }));
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Unable to load event details.';
        setDetailErrorById((current) => ({ ...current, [eventId]: message }));
      } finally {
        setDetailLoadingId((current) => (current === eventId ? null : current));
      }
    },
    [eventDetailsById, expandedEventId],
  );

  const loadEvents = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const [discoveredEvents, discoveryFeed] = await Promise.all([
          listDiscoverableEvents(requestFilters),
          listDiscoverableEvents({ dateBucket: 'upcoming' }),
        ]);
        setEvents(discoveredEvents);
        setFeaturedEvents(discoveryFeed);
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

  const listHeader = (
    <>
      <View style={styles.header}>
        <View>
          <Text style={styles.kicker}>DISCOVER</Text>
          <Text style={styles.title}>Admitly</Text>
        </View>
        <View style={styles.headerLinks}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}
            onPress={onOpenNotifications}
            style={styles.notificationButton}
          >
            <Text style={styles.notificationIcon}>🔔</Text>
            {unreadCount > 0 ? <Text style={styles.notificationBadge}>{unreadCount > 99 ? '99+' : unreadCount}</Text> : null}
          </Pressable>
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

      {featuredSubset.length > 0 ? (
        <View style={styles.featuredSection}>
          <Text style={styles.featuredTitle}>Featured Events</Text>
          <ScrollView
            horizontal
            nestedScrollEnabled
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.featuredRow}
          >
            {featuredSubset.map((item) => (
              <View key={item.id} style={styles.featuredCardWrap}>
                <EventCard event={item} onPress={() => onOpenEvent(item.id)} />
                <View style={styles.featuredActions}>
                  <Pressable style={[styles.featuredActionButton, styles.featuredSecondaryAction]} onPress={() => onOpenEvent(item.id)}>
                    <Text style={styles.featuredSecondaryActionText}>Details</Text>
                  </Pressable>
                  <Pressable style={[styles.featuredActionButton, styles.featuredPrimaryAction]} onPress={() => onGetTickets(item.id)}>
                    <Text style={styles.featuredPrimaryActionText}>Get Tickets</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </ScrollView>
        </View>
      ) : null}
    </>
  );

  const listFooter = (
    <Pressable onPress={onSignOut} style={styles.signOutArea}>
      <Text style={styles.signOutText}>Sign out</Text>
    </Pressable>
  );

  const listEmpty = loading ? (
    <View style={styles.stateWrap}>
      <ActivityIndicator color={theme.colors.primary} />
      <Text style={styles.stateText}>Loading events...</Text>
    </View>
  ) : error ? (
    <View style={styles.stateWrap}>
      <Text style={styles.errorText}>{error}</Text>
      <ThemedButton label="Try Again" onPress={() => loadEvents()} variant="secondary" />
    </View>
  ) : (
    <View style={styles.stateWrap}>
      <Text style={styles.stateText}>No events match your filters.</Text>
      <ThemedButton label="Reset Filters" onPress={resetFilters} />
      {hasActiveFilters && featuredSubset.length > 0 ? (
        <View style={styles.emptyDiscovery}>
          <Text style={styles.emptyDiscoveryTitle}>Explore featured picks</Text>
          {featuredSubset.slice(0, 2).map((item) => (
            <EventCard
              key={`empty-${item.id}`}
              event={item}
              expanded={expandedEventId === item.id}
              detail={eventDetailsById[item.id]}
              detailLoading={detailLoadingId === item.id}
              detailError={detailErrorById[item.id]}
              onPress={() => toggleEventExpansion(item.id)}
              onCollapse={() => toggleEventExpansion(item.id)}
              onGetTickets={() => onGetTickets(item.id)}
            />
          ))}
        </View>
      ) : null}
    </View>
  );

  return (
    <Screen padded={false}>
      <View style={styles.container}>
        <FlatList
          data={loading || error ? [] : events}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={styles.homeListContent}
          renderItem={({ item, index }) => (
            <View style={[styles.eventListItem, index === 0 && styles.firstEventListItem]}>
              <EventCard
                event={item}
                expanded={expandedEventId === item.id}
                detail={eventDetailsById[item.id]}
                detailLoading={detailLoadingId === item.id}
                detailError={detailErrorById[item.id]}
                onPress={() => toggleEventExpansion(item.id)}
                onCollapse={() => toggleEventExpansion(item.id)}
                onGetTickets={() => onGetTickets(item.id)}
              />
            </View>
          )}
          ListHeaderComponent={listHeader}
          ListEmptyComponent={listEmpty}
          ListFooterComponent={listFooter}
          keyboardShouldPersistTaps="handled"
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => loadEvents(true)}
              tintColor={theme.colors.primary}
            />
          }
        />
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
  headerLinks: { flexDirection: 'row', gap: theme.spacing.sm, alignItems: 'center' },
  notificationButton: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  notificationIcon: { fontSize: 20 },
  notificationBadge: { position: 'absolute', right: 0, top: 0, minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 3, backgroundColor: theme.colors.error, color: '#fff', fontSize: 10, fontWeight: '700', textAlign: 'center', lineHeight: 18, overflow: 'hidden' },
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
  homeListContent: {
    paddingBottom: theme.spacing.xl,
  },
  eventListItem: {
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.md,
  },
  firstEventListItem: {
    marginTop: theme.spacing.sm,
  },
  stateWrap: {
    paddingHorizontal: theme.spacing.lg,
    alignItems: 'center',
    gap: theme.spacing.md,
    marginTop: theme.spacing.xl,
  },
  featuredSection: {
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  featuredTitle: {
    color: theme.colors.textPrimary,
    fontSize: theme.typography.body,
    fontWeight: '700',
    paddingHorizontal: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  featuredRow: {
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingRight: theme.spacing.xl,
  },
  featuredCardWrap: {
    width: 290,
    gap: theme.spacing.sm,
  },
  featuredActions: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  featuredActionButton: {
    flex: 1,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    paddingVertical: theme.spacing.sm,
    alignItems: 'center',
  },
  featuredPrimaryAction: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  featuredSecondaryAction: {
    backgroundColor: theme.colors.surface,
    borderColor: theme.colors.primaryMuted,
  },
  featuredPrimaryActionText: {
    color: '#090909',
    fontWeight: '700',
  },
  featuredSecondaryActionText: {
    color: theme.colors.primary,
    fontWeight: '700',
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
  emptyDiscovery: {
    marginTop: theme.spacing.sm,
    gap: theme.spacing.md,
  },
  emptyDiscoveryTitle: {
    color: theme.colors.textPrimary,
    fontWeight: '600',
    textAlign: 'center',
  },
});
