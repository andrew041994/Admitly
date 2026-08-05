const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, 'TicketDetailScreen.tsx'), 'utf8');

test('recipient lookup and final transfer creation are separate mobile actions', () => {
  const lookupHandler = source.slice(source.indexOf('async function continueToConfirmation'), source.indexOf('async function submitTransfer'));
  const createHandler = source.slice(source.indexOf('async function submitTransfer'), source.indexOf('if (loadError)'));
  assert.match(lookupHandler, /resolveTicketTransferRecipient/);
  assert.doesNotMatch(lookupHandler, /createTicketTransfer\(/);
  assert.match(createHandler, /createTicketTransfer\(/);
  assert.match(source, /label="Continue"/);
  assert.match(source, /label="Transfer ticket"/);
  assert.match(source, /label="Cancel"/);
});

test('confirmation displays verified recipient and ticket context before creation', () => {
  assert.match(source, /resolution\.recipient_display_name/);
  assert.match(source, /resolution\.recipient_email/);
  assert.match(source, /ticket\.event\.title/);
  assert.match(source, /ticket\.ticket_tier_name/);
  assert.match(source, /formatDate\(ticket\.event\.start_at\)/);
  assert.match(source, /Ownership moves only after the recipient accepts/);
});

test('phone is disabled and missing profile phone cannot gate email transfer', () => {
  assert.match(source, /PHONE_TRANSFER_LABEL/);
  assert.doesNotMatch(source, /getAccountProfile|hasPhone|recipientType/);
});

test('expired references return to lookup and uncertain requests reconcile against outgoing transfers', () => {
  assert.match(source, /err\.status === 410/);
  assert.match(source, /setResolution\(null\)/);
  assert.match(source, /listMyTicketTransfers\('outgoing'\)/);
  assert.match(source, /item\.ticket_id === ticketId && item\.status === 'pending'/);
});
