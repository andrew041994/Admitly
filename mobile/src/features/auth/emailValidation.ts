const LOCAL_PART = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$/;
const DOMAIN_LABEL = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/;

export function normalizeEmailAddress(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized.length > 254 || normalized.includes(' ')) return null;
  if ((normalized.match(/@/g) ?? []).length !== 1) return null;
  const [local, domain] = normalized.split('@');
  if (!local || local.length > 64 || !LOCAL_PART.test(local)) return null;
  if (local.startsWith('.') || local.endsWith('.') || local.includes('..')) return null;
  const labels = domain.split('.');
  if (labels.length < 2 || labels.some((label) => !DOMAIN_LABEL.test(label))) return null;
  return normalized;
}
