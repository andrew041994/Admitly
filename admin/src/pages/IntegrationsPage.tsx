import { useEffect, useState } from 'react';
import { createApiKey, createWebhook, listApiKeys, listDeliveries, listWebhooks, redeliverDelivery } from '../lib/integrationsApi';

const adminUserId = 1;

function statusLabel(item: any) {
  const retryInfo = item.next_retry_at ? ` • retry at ${new Date(item.next_retry_at).toLocaleString()}` : '';
  const failure = item.failure_reason ? ` • ${item.failure_reason}` : '';
  return `${item.status}${item.response_status_code ? ` (${item.response_status_code})` : ''}${retryInfo}${failure}`;
}

export function IntegrationsPage() {
  const [keys, setKeys] = useState<any[]>([]);
  const [webhooks, setWebhooks] = useState<any[]>([]);
  const [deliveries, setDeliveries] = useState<any[]>([]);
  const [rawKey, setRawKey] = useState<string | null>(null);
  const [rawSecret, setRawSecret] = useState<string | null>(null);

  async function load() {
    setKeys(await listApiKeys(adminUserId));
    setWebhooks(await listWebhooks(adminUserId));
    setDeliveries(await listDeliveries(adminUserId));
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <section>
      <h2>Integrations</h2>
      <p>Manage API credentials, webhook endpoints, and delivery logs.</p>
      <div className="finance-card-grid">
        <article className="finance-card">
          <h3>Create API key</h3>
          <button onClick={async () => {
            const created = await createApiKey(adminUserId, { name: `Key ${Date.now()}`, scopes: ['integrations:read', 'integrations:write'] });
            setRawKey(created.raw_key);
            await load();
          }}>Generate key</button>
          {rawKey ? <p>Created key (copy now; shown once): <code>{rawKey}</code></p> : null}
          <ul>{keys.map((key) => <li key={key.id}>{key.name} — {key.key_prefix} — {key.scopes.join(', ')} — last used: {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : 'never'} — {key.revoked_at ? 'revoked' : 'active'}</li>)}</ul>
        </article>
        <article className="finance-card">
          <h3>Create webhook</h3>
          <button onClick={async () => {
            const created = await createWebhook(adminUserId, { name: `Endpoint ${Date.now()}`, target_url: 'https://example.com/webhooks/admitly', subscribed_events: ['order.paid', 'refund.processed'] });
            setRawSecret(created.signing_secret);
            await load();
          }}>Add webhook</button>
          {rawSecret ? <p>Signing secret (copy now): <code>{rawSecret}</code></p> : null}
          <ul>{webhooks.map((item) => <li key={item.id}>{item.name} — {item.target_url} — {item.is_active ? 'enabled' : 'disabled'} — events: {item.subscribed_events.join(', ')}</li>)}</ul>
        </article>
      </div>
      <article className="finance-card">
        <h3>Recent deliveries</h3>
        <ul>
          {deliveries.slice(0, 15).map((item) => (
            <li key={item.id}>
              {item.event_type} ({item.event_id}) #{item.attempt_number} — {item.delivery_kind} — {statusLabel(item)}
              {' '}
              <button onClick={async () => { await redeliverDelivery(adminUserId, item.id); await load(); }}>Redeliver</button>
            </li>
          ))}
        </ul>
      </article>
    </section>
  );
}
