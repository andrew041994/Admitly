const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const screenSource = fs.readFileSync(path.join(__dirname, 'CreateEventScreen.tsx'), 'utf8');
const apiSource = fs.readFileSync(path.join(__dirname, '..', '..', 'api', 'organizer.ts'), 'utf8');

test('event cover upload is bound to a created event', () => {
  assert.match(apiSource, /path: `\/events\/\$\{eventId\}\/cover-image`/);
  assert.doesNotMatch(apiSource, /path: ['"]\/events\/uploads\/cover-image/);
  assert.ok(screenSource.indexOf('await createEvent(') < screenSource.indexOf('await uploadEventCoverImage(eventId, coverImageFile)'));
  assert.doesNotMatch(screenSource, /cover_image_url:/);
});

test('failed cover attachment retries without creating a duplicate event', () => {
  assert.match(screenSource, /const \[createdEventId, setCreatedEventId\]/);
  assert.match(screenSource, /if \(eventId === null\)/);
  assert.match(screenSource, /setCreatedEventId\(eventId\)/);
  assert.match(screenSource, /Retry Cover Upload/);
});
