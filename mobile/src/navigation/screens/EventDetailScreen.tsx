import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { EventDiscoveryDetail, getDiscoverableEventDetail } from '../../api/events';
import { Screen } from '../../components/Screen';
import { ThemedButton } from '../../components/ThemedButton';
import { formatEventDateRange, formatPriceLabel, formatVenueLabel } from '../../features/events/formatters';
import { textStyles, theme } from '../../theme';

type EventDetailScreenProps = {
  eventId: number;
  onGetTickets: (event: EventDiscoveryDetail) => void;
};

export function EventDetailScreen({ eventId, onGetTickets }: EventDetailScreenProps) {
  const [event, setEvent] = useState<EventDiscoveryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadEvent() {
      setLoading(true);
      try {
        const eventDetail = await getDiscoverableEventDetail(eventId);
        setEvent(eventDetail);
        setError(null);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Unable to load event details.';
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    loadEvent();
  }, [eventId]);

  if (loading) {
    return (
      <Screen>
        <View style={styles.stateWrap}>
          <ActivityIndicator color={theme.colors.primary} />
          <Text style={styles.stateText}>Loading event...</Text>
        </View>
      </Screen>
    );
  }

  if (error || !event) {
    return (
      <Screen>
        <View style={styles.stateWrap}>
          <Text style={styles.errorText}>{error ?? 'Event not found.'}</Text>
        </View>
      </Screen>
    );
  }

  return (
    <Screen padded={false}>
      <ScrollView contentContainerStyle={styles.content}>
        {event.cover_image_url ? <Image source={{ uri: event.cover_image_url }} style={styles.hero} /> : <View style={styles.heroFallback} />}

        <View style={styles.body}>
          {event.category ? <Text style={styles.category}>{event.category.toUpperCase()}</Text> : null}
          <Text style={textStyles.heading}>{event.title}</Text>
          <Text style={styles.meta}>{formatEventDateRange(event.start_at, event.end_at)}</Text>
          <Text style={styles.meta}>
            {formatVenueLabel({
              venueName: event.venue_name,
              venueCity: event.venue_city,
              venueCountry: event.venue_country,
              customVenueName: event.custom_venue_name,
              customAddressText: event.custom_address_text,
            })}
          </Text>
          {event.organizer_name ? <Text style={styles.meta}>By {event.organizer_name}</Text> : null}
          {formatPriceLabel(event.price_summary) ? <Text style={styles.price}>{formatPriceLabel(event.price_summary)}</Text> : null}

          <Text style={styles.sectionTitle}>About this event</Text>
          <Text style={styles.description}>{event.long_description ?? event.short_description ?? 'Details coming soon.'}</Text>

          <View style={styles.ctaPanel}>
            <Text style={styles.ctaTitle}>Tickets</Text>
            <Text style={styles.ctaSubtitle}>Choose tickets and complete checkout.</Text>
            <ThemedButton label="Get Tickets" onPress={() => onGetTickets(event)} disabled={!event.ticket_tiers?.some((tier) => tier.is_active && tier.available_quantity > 0)} />
          </View>
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: theme.spacing.xl,
  },
  hero: {
    width: '100%',
    height: 260,
  },
  heroFallback: {
    width: '100%',
    height: 180,
    backgroundColor: theme.colors.surfaceElevated,
  },
  body: {
    padding: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  category: {
    color: theme.colors.primary,
    fontSize: theme.typography.caption,
    letterSpacing: 1.2,
    fontWeight: '700',
  },
  meta: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.label,
  },
  price: {
    color: theme.colors.primary,
    fontWeight: '700',
    marginTop: theme.spacing.xs,
  },
  sectionTitle: {
    color: theme.colors.textPrimary,
    fontWeight: '700',
    marginTop: theme.spacing.md,
  },
  description: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.body,
    lineHeight: 24,
  },
  ctaPanel: {
    marginTop: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.primaryMuted,
    borderRadius: theme.radius.lg,
    backgroundColor: '#171208',
    padding: theme.spacing.md,
    gap: theme.spacing.sm,
  },
  ctaTitle: {
    color: theme.colors.primary,
    fontWeight: '700',
  },
  ctaSubtitle: {
    color: theme.colors.textSecondary,
  },
  stateWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing.md,
  },
  stateText: {
    color: theme.colors.textSecondary,
  },
  errorText: {
    color: theme.colors.error,
  },
});
