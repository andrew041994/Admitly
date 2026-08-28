const sensitiveQueryKeys = new Set(['token', 'access_token', 'refresh_token']);
const sensitiveFileKeys = ['filename', 'fileName', 'file_name'];

export function redactSensitiveUrl(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try {
    const parsed = new URL(value, window.location.origin);
    for (const key of sensitiveQueryKeys) if (parsed.searchParams.has(key)) parsed.searchParams.set(key, '[Filtered]');
    return value.startsWith('http') ? parsed.toString() : `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return value;
  }
}

export function scrubSentryBreadcrumb<T extends { data?: Record<string, unknown> }>(breadcrumb: T): T {
  const data = breadcrumb.data && typeof breadcrumb.data === 'object' ? { ...breadcrumb.data as Record<string, unknown> } : undefined;
  if (data?.url) data.url = redactSensitiveUrl(data.url);
  if (data?.from) data.from = redactSensitiveUrl(data.from);
  if (data?.to) data.to = redactSensitiveUrl(data.to);
  for (const key of sensitiveFileKeys) if (key in (data ?? {})) data![key] = '[Filtered]';
  return { ...breadcrumb, ...(data ? { data } : {}) };
}

export function scrubSentryEvent<T extends { request?: { url?: string }; breadcrumbs?: Array<{ data?: Record<string, unknown> }> }>(event: T): T {
  if (event.request?.url) event.request.url = redactSensitiveUrl(event.request.url) as string;
  if (event.breadcrumbs) event.breadcrumbs = event.breadcrumbs.map(scrubSentryBreadcrumb);
  return event;
}
