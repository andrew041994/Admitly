export const ACTIVE_TRANSFER_METHODS = ['email'] as const;

export function normalizeTransferEmail(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized.length > 254 || normalized.includes(' ')) return null;
  if ((normalized.match(/@/g) ?? []).length !== 1) return null;
  const [local, domain] = normalized.split('@');
  if (!local || local.length > 64 || !/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)) return null;
  if (local.startsWith('.') || local.endsWith('.') || local.includes('..')) return null;
  const labels = domain.split('.');
  if (labels.length < 2 || labels.some((label) => !/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))) return null;
  return normalized;
}

export function maskTransferIdentifier(value: string): string {
  if (value.includes('@')) {
    const [local, domain] = value.split('@', 2);
    const shown = local.slice(0, local.length > 2 ? 2 : 1);
    return `${shown}${'*'.repeat(Math.max(1, local.length - shown.length))}@${domain}`;
  }
  const digits = value.replace(/\D/g, '');
  return `+${'*'.repeat(Math.max(0, digits.length - 4))}${digits.slice(-4)}`;
}

export function canSubmitTransfer(identifier: string | null, submitting: boolean): boolean {
  return Boolean(identifier) && !submitting;
}

export function canCreateResolvedTransfer(reference: string | null, submitting: boolean): boolean {
  return Boolean(reference) && !submitting;
}

export function isPendingTransfer(status: string): boolean {
  return status === 'pending';
}
