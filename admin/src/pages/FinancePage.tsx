import { FormEvent, useMemo, useState } from 'react';
import { ApiError } from '../lib/apiClient';
import { apiBaseUrl } from '../lib/config';
import { buildOrdersExportUrl, fetchAdminFinanceOrders, fetchAdminFinanceSummary, FinanceOrderRow } from '../lib/financeApi';

function formatMoney(amount: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
}

export function FinancePage() {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [orders, setOrders] = useState<FinanceOrderRow[]>([]);

  const onLoad = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const [summaryData, orderData] = await Promise.all([
        fetchAdminFinanceSummary(dateFrom || undefined, dateTo || undefined),
        fetchAdminFinanceOrders(dateFrom || undefined, dateTo || undefined),
      ]);
      setSummary(summaryData);
      setOrders(orderData);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load finance reporting.');
    } finally {
      setLoading(false);
    }
  };

  const cards = useMemo(() => {
    if (!summary) return [];
    return [
      ['Gross sales', formatMoney(summary.gross_sales_amount, summary.currency)],
      ['Refunded', formatMoney(summary.refunded_amount, summary.currency)],
      ['Disputes', formatMoney(summary.dispute_amount, summary.currency)],
      ['Discounts', formatMoney(summary.discount_amount, summary.currency)],
      ['Comp value', formatMoney(summary.comp_amount, summary.currency)],
      ['Organizer net', formatMoney(summary.organizer_net_amount, summary.currency)],
      ['Settled', formatMoney(summary.settled_amount, summary.currency)],
      ['Pending payout', formatMoney(summary.pending_payout_amount, summary.currency)],
    ];
  }, [summary]);

  return (
    <section className="support-page" aria-labelledby="finance-title">
      <header>
        <h2 id="finance-title">Finance Reporting</h2>
      </header>
      <div className="card">
        <form className="lookup-row" onSubmit={onLoad}>
          <label>
            Date from
            <input type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            Date to
            <input type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button type="submit" disabled={loading}>{loading ? 'Loading…' : 'Load report'}</button>
        </form>
        <p className="muted-text">Date range uses paid_at with inclusive date_from and exclusive date_to.</p>
        <button type="button" onClick={() => window.open(`${apiBaseUrl}${buildOrdersExportUrl(dateFrom || undefined, dateTo || undefined)}`, '_blank')}>
          Export orders CSV
        </button>
        {error ? <p className="error-text">{error}</p> : null}
      </div>

      {cards.length ? (
        <div className="support-grid">
          <div className="card">
            <h3>Summary</h3>
            <dl className="kv-list">
              {cards.map(([label, value]) => (
                <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
              ))}
              <div><dt>Refunded orders</dt><dd>{summary.refunded_order_count}</dd></div>
              <div><dt>Dispute count</dt><dd>{summary.dispute_count}</dd></div>
              <div><dt>Promo usage</dt><dd>{summary.promo_usage_count}</dd></div>
            </dl>
          </div>

          <div className="card">
            <h3>Order rows</h3>
            <table className="finance-table">
              <thead><tr><th>Order</th><th>Status</th><th>Payout</th><th>Total</th><th>Refunded</th><th>Paid at</th></tr></thead>
              <tbody>
                {orders.map((row) => (
                  <tr key={row.order_id}>
                    <td>#{row.order_id}</td>
                    <td>{row.status}/{row.refund_status}</td>
                    <td>{row.payout_status}</td>
                    <td>{formatMoney(row.total_amount, row.currency)}</td>
                    <td>{formatMoney(row.refunded_amount, row.currency)}</td>
                    <td>{row.completed_at ? new Date(row.completed_at).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
