import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { EventDiscoveryItem } from '../../api/events';
import { textStyles, theme } from '../../theme';
import { formatEventDateRange, formatPriceLabel, formatVenueLabel } from '../../features/events/formatters';

type EventCardProps = {
  event: EventDiscoveryItem;
  onPress: () => void;
};

export function EventCard({ event, onPress }: EventCardProps) {
  const dateLabel = formatEventDateRange(event.start_at, event.end_at);
  const venueLabel = formatVenueLabel({
    venueName: event.venue_name,
    venueCity: event.venue_city,
    venueCountry: event.venue_country,
    customVenueName: event.custom_venue_name,
    customAddressText: event.custom_address_text,
  });
  const priceLabel = formatPriceLabel(event.price_summary);

  return (
    <Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]} onPress={onPress}>
      {event.cover_image_url ? <Image source={{ uri: event.cover_image_url }} style={styles.image} /> : <View style={styles.imageFallback} />}
      <View style={styles.body}>
        {event.category ? <Text style={styles.category}>{event.category.toUpperCase()}</Text> : null}
        <Text style={textStyles.label}>{event.title}</Text>
        {!!event.short_description ? (
          <Text numberOfLines={2} style={styles.description}>
            {event.short_description}
          </Text>
        ) : null}
        <Text style={styles.meta}>{dateLabel}</Text>
        <Text style={styles.meta}>{venueLabel}</Text>
        {priceLabel ? <Text style={styles.price}>{priceLabel}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: theme.radius.lg,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    overflow: 'hidden',
  },
  pressed: {
    opacity: 0.9,
  },
  image: {
    width: '100%',
    height: 180,
  },
  imageFallback: {
    height: 120,
    backgroundColor: theme.colors.surfaceElevated,
  },
  body: {
    padding: theme.spacing.md,
    gap: theme.spacing.xs,
  },
  category: {
    color: theme.colors.primary,
    fontSize: theme.typography.caption,
    letterSpacing: 1.2,
    fontWeight: '700',
  },
  description: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.label,
  },
  meta: {
    color: theme.colors.textSecondary,
    fontSize: theme.typography.caption,
  },
  price: {
    color: theme.colors.primary,
    marginTop: theme.spacing.xs,
    fontWeight: '600',
  },
});
