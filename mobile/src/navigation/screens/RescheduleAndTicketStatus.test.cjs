const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const read = (relativePath) => fs.readFileSync(path.join(__dirname, relativePath), 'utf8');

test('approved event dashboard exposes the dedicated reschedule workflow', () => {
  const dashboard = read('OrganizerDashboardScreen.tsx');
  const screen = read('RescheduleEventScreen.tsx');
  const api = read('../../api/organizer.ts');

  assert.match(dashboard, /approval_status === 'approved'/);
  assert.match(dashboard, /Reschedule or Change Venue/);
  assert.match(api, /\/events\/organizer\/events\/\$\{eventId\}\/reschedule/);
  assert.match(screen, /idempotency_key: idempotencyKey/);
  assert.match(screen, /reason: trimmedReason/);
  assert.match(screen, /Existing tickets and check-in codes remain valid/);
  assert.match(screen, /Current venue/);
  assert.match(screen, /New venue/);
});

test('ticket UI recognizes only canonical user-facing statuses', () => {
  const api = read('../../api/tickets.ts');
  const wallet = read('MyTicketsScreen.tsx');
  const detail = read('TicketDetailScreen.tsx');

  assert.match(api, /'active' \| 'used' \| 'expired' \| 'refunded'/);
  for (const label of ['Active', 'Used', 'Expired', 'Refunded']) {
    assert.match(wallet, new RegExp(label));
  }
  assert.doesNotMatch(wallet, /return 'Invalid'/);
  assert.match(detail, /ticket\.can_display_entry_code \? \(/);
});
