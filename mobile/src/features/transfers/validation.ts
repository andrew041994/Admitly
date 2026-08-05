export type TransferRecipientType = 'email' | 'phone';

export const ACTIVE_TRANSFER_METHODS = ['email'] as const;
export const PHONE_TRANSFER_LABEL = 'Phone transfer — coming after phone verification';

export function normalizePhoneNumber(value: string): string | null {
  const raw = value.trim();
  if (!raw) return null;
  if (!/^[+0-9().\-\s]+$/.test(raw)) return null;
  const explicitInternational = raw.startsWith('+') || raw.startsWith('00');
  let digits = raw.replace(/\D/g, '');
  if (raw.startsWith('00')) digits = digits.slice(2);
  else if (!explicitInternational) {
    if (digits.length === 7) digits = `592${digits}`;
    else if (digits.length === 10) digits = `1${digits}`;
    else return null;
  }
  if (digits.length < 8 || digits.length > 15 || digits.startsWith('0')) return null;
  return `+${digits}`;
}

export function normalizeTransferIdentifier(type: TransferRecipientType, value: string): string | null {
  if (type === 'phone') return normalizePhoneNumber(value);
  const normalized = value.trim().toLowerCase();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized) && normalized.length <= 255 ? normalized : null;
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
