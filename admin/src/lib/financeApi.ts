import { apiRequest } from './apiClient';

export type AdminFinanceSummary = {
  gross_sales_amount: number;
  refunded_amount: number;
  dispute_amount: number;
  discount_amount: number;
  promo_discount_amount: number;
  comp_amount: number;
  platform_fee_amount: number;
  organizer_net_amount: number;
  settled_amount: number;
  pending_payout_amount: number;
  payout_eligible_amount: number;
  refunded_order_count: number;
  dispute_count: number;
  promo_usage_count: number;
  reconciliation_exception_count: number;
  order_count: number;
  currency: string;
};

export type FinanceOrderRow = {
  order_id: number;
  buyer_user_id: number;
  status: string;
  refund_status: string;
  reconciliation_status: string;
  payout_status: string;
  total_amount: number;
  refunded_amount: number;
  payout_eligible_amount: number;
  currency: string;
  completed_at: string | null;
};

const asQuery = (params: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  const suffix = search.toString();
  return suffix ? `?${suffix}` : '';
};

export async function fetchAdminFinanceSummary(dateFrom?: string, dateTo?: string) {
  const response = await apiRequest(`/admin/finance/summary${asQuery({ date_from: dateFrom, date_to: dateTo })}`);
  return (await response.json()) as AdminFinanceSummary;
}

export async function fetchAdminFinanceOrders(dateFrom?: string, dateTo?: string) {
  const response = await apiRequest(`/admin/finance/orders${asQuery({ date_from: dateFrom, date_to: dateTo, limit: '100' })}`);
  return (await response.json()) as FinanceOrderRow[];
}

export function buildOrdersExportUrl(dateFrom?: string, dateTo?: string) {
  return `/admin/finance/orders/export.csv${asQuery({ date_from: dateFrom, date_to: dateTo })}`;
}
