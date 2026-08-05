const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const file = path.join(__dirname, 'routing.ts');
const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleShim = { exports: {} };
new Function('require', 'module', 'exports', output)(require, moduleShim, moduleShim.exports);
const { getNotificationDestination } = moduleShim.exports;

assert.deepEqual(getNotificationDestination({ route_key: 'ticket', route_params: { ticket_id: 4 } }), { screen: 'TicketDetail', params: { ticketId: 4 } });
assert.deepEqual(getNotificationDestination({ routeKey: 'event', event_id: '8' }), { screen: 'EventDetail', params: { eventId: 8 } });
assert.deepEqual(getNotificationDestination({ route_key: 'transfers' }), { screen: 'MyTickets' });
assert.equal(getNotificationDestination({ route_key: 'https://evil.example' }), null);
assert.equal(getNotificationDestination({ route_key: 'ticket', ticket_id: '../2' }), null);
console.log('notification routing tests passed');
