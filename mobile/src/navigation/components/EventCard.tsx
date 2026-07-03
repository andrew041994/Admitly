import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { EventDiscoveryDetail, EventDiscoveryItem } from '../../api/events';
import { ThemedButton } from '../../components/ThemedButton';
import { textStyles, theme } from '../../theme';
import { formatEventDateRange, formatPriceLabel, formatVenueLabel } from '../../features/events/formatters';

type EventCardProps = {
  event: EventDiscoveryItem;
  onPress: () => void;
  expanded?: boolean;
  detail?: EventDiscoveryDetail | null;
  detailLoading?: boolean;
  detailError?: string | null;
  onGetTickets?: () => void;
  onCollapse?: () => void;
};

export function EventCard({
  event,
  onPress,
  expanded = false,
  detail,
  detailLoading = false,
  detailError = null,
  onGetTickets,
  onCollapse,
}: EventCardProps) {
  const displayEvent = detail ?? event;
  const dateLabel = formatEventDateRange(displayEvent.start_at, displayEvent.end_at);
  const venueLabel = formatVenueLabel({
    venueName: displayEvent.venue_name,
    venueCity: displayEvent.venue_city,
    venueCountry: displayEvent.venue_country,
    customVenueName: displayEvent.custom_venue_name,
    customAddressText: displayEvent.custom_address_text,
  });
  const priceLabel = formatPriceLabel(displayEvent.price_summary) ?? 'Price details coming soon';
  const description = detail?.long_description ?? displayEvent.short_description ?? 'Details coming soon.';
  const ticketsAvailable = detail?.ticket_tiers?.some((tier) => tier.is_active && tier.available_quantity > 0) ?? true;

  return (
    <View style={styles.card}>
      <Pressable style={({ pressed }) => [styles.heroButton, pressed && styles.pressed]} onPress={onPress}>
        <View style={styles.imageWrap}>
          {event.cover_image_url ? (
            <Image source={{ uri: event.cover_image_url }} style={styles.image} resizeMode="contain" />
          ) : (
            <View style={styles.imageFallback}>
              <View style={styles.fallbackOrbLarge} />
              <View style={styles.fallbackOrbSmall} />
              <Text style={styles.fallbackBrand}>ADMITLY</Text>
            </View>
          )}
          <View style={styles.topScrim} />
          <View style={styles.bottomScrim} />
          {event.category ? <Text style={styles.categoryBadge}>{event.category.toUpperCase()}</Text> : null}
          <View style={styles.heroText}>
            <Text numberOfLines={2} style={styles.heroTitle}>{event.title}</Text>
            <Text numberOfLines={1} style={styles.heroDate}>{formatEventDateRange(event.start_at, event.end_at)}</Text>
          </View>
        </View>
      </Pressable>

      {expanded ? (
        <View style={styles.expandedBody}>
          {detailLoading ? <Text style={styles.meta}>Loading event details...</Text> : null}
          {detailError ? <Text style={styles.errorText}>{detailError}</Text> : null}

          <View style={styles.detailHeader}>
            <View style={styles.detailTitleWrap}>
              {displayEvent.category ? <Text style={styles.category}>{displayEvent.category.toUpperCase()}</Text> : null}
              <Text style={textStyles.heading}>{displayEvent.title}</Text>
            </View>
            {onCollapse ? (
              <Pressable onPress={onCollapse} hitSlop={10}>
                <Text style={styles.collapseText}>Collapse</Text>
              </Pressable>
            ) : null}
          </View>

          <Text style={styles.description}>{description}</Text>

          <View style={styles.detailsGrid}>
            <DetailRow label="Date & time" value={dateLabel} />
            <DetailRow label="Venue" value={venueLabel} />
            {detail?.organizer_name ? <DetailRow label="Organizer" value={detail.organizer_name} /> : null}
            <DetailRow label="Tickets" value={priceLabel} highlight />
          </View>

          <ThemedButton
            label="Get Tickets"
            onPress={onGetTickets ?? onPress}
            disabled={!ticketsAvailable || detailLoading || Boolean(detailError)}
          />
          {!ticketsAvailable && detail ? <Text style={styles.unavailableText}>Tickets are currently unavailable.</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

function DetailRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, highlight && styles.detailValueHighlight]}>{value}</Text>
    </View>
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
  heroButton: { overflow: 'hidden' },
  pressed: { opacity: 0.92 },
  imageWrap: { width: '100%', aspectRatio: 4 / 5, overflow: 'hidden', backgroundColor: theme.colors.surfaceElevated },
  image: { width: '100%', height: '100%' },
  imageFallback: { flex: 1, backgroundColor: '#120F05', justifyContent: 'center', alignItems: 'center' },
  fallbackOrbLarge: { position: 'absolute', width: 220, height: 220, borderRadius: 110, backgroundColor: '#3B2E0B', right: -50, top: -40, opacity: 0.75 },
  fallbackOrbSmall: { position: 'absolute', width: 150, height: 150, borderRadius: 75, backgroundColor: theme.colors.primaryMuted, left: -35, bottom: -45, opacity: 0.35 },
  fallbackBrand: { color: theme.colors.primary, fontWeight: '800', letterSpacing: 4 },
  topScrim: { position: 'absolute', top: 0, left: 0, right: 0, height: 82, backgroundColor: 'rgba(0,0,0,0.24)' },
  bottomScrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 150, backgroundColor: 'rgba(0,0,0,0.58)' },
  categoryBadge: { position: 'absolute', top: theme.spacing.md, left: theme.spacing.md, color: theme.colors.primary, backgroundColor: 'rgba(5,5,5,0.72)', borderColor: 'rgba(212,175,55,0.55)', borderWidth: 1, borderRadius: 999, overflow: 'hidden', paddingHorizontal: theme.spacing.sm, paddingVertical: theme.spacing.xs, fontSize: theme.typography.caption, letterSpacing: 1.1, fontWeight: '800' },
  heroText: { position: 'absolute', left: theme.spacing.md, right: theme.spacing.md, bottom: theme.spacing.md, gap: theme.spacing.xs },
  heroTitle: { color: theme.colors.textPrimary, fontSize: 24, lineHeight: 30, fontWeight: '800' },
  heroDate: { color: theme.colors.textPrimary, fontSize: theme.typography.label, fontWeight: '600' },
  expandedBody: { padding: theme.spacing.md, gap: theme.spacing.md },
  detailHeader: { flexDirection: 'row', justifyContent: 'space-between', gap: theme.spacing.md, alignItems: 'flex-start' },
  detailTitleWrap: { flex: 1, gap: theme.spacing.xs },
  category: { color: theme.colors.primary, fontSize: theme.typography.caption, letterSpacing: 1.2, fontWeight: '700' },
  collapseText: { color: theme.colors.primary, fontWeight: '700' },
  description: { color: theme.colors.textSecondary, fontSize: theme.typography.body, lineHeight: 24 },
  meta: { color: theme.colors.textSecondary, fontSize: theme.typography.label },
  errorText: { color: theme.colors.error },
  detailsGrid: { borderTopWidth: 1, borderTopColor: theme.colors.border },
  detailRow: { paddingVertical: theme.spacing.sm, borderBottomWidth: 1, borderBottomColor: theme.colors.border, gap: theme.spacing.xs },
  detailLabel: { color: theme.colors.textSecondary, fontSize: theme.typography.caption, textTransform: 'uppercase', letterSpacing: 0.8 },
  detailValue: { color: theme.colors.textPrimary, fontSize: theme.typography.label, lineHeight: 20 },
  detailValueHighlight: { color: theme.colors.primary, fontWeight: '700' },
  unavailableText: { color: theme.colors.textSecondary, textAlign: 'center', fontSize: theme.typography.caption },
});
