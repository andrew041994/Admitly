import { ApiError } from '../../api/client';

export type ScanUiState = 'requesting_permission' | 'permission_denied' | 'ready' | 'processing' | 'success' | 'error';

export type ScanOutcome =
  | 'success'
  | 'already_used'
  | 'invalid'
  | 'wrong_event'
  | 'unauthorized'
  | 'network_error'
  | 'server_error';

export type ScanResult = {
  outcome: ScanOutcome;
  title: string;
  message: string;
  attendeeName?: string;
  ticketType?: string;
  checkedInAt?: string;
};

export type ScanApiSuccessResponse = {
  state?: string;
  status?: string;
  result?: string;
  attendee_name?: string;
  ticket_type?: string;
  checked_in_at?: string;
  message?: string;
};

const DUPLICATE_WINDOW_MS = 2500;

function normalizeState(value?: string) {
  return value?.trim().toLowerCase();
}

export function shouldIgnoreDuplicateScan(
  rawValue: string,
  lastScanRawValue: string | null,
  lastScanAt: number,
  now: number,
) {
  if (!rawValue.trim()) {
    return true;
  }

  if (!lastScanRawValue) {
    return false;
  }

  return rawValue === lastScanRawValue && now - lastScanAt < DUPLICATE_WINDOW_MS;
}

export function mapScanResponseToResult(response: ScanApiSuccessResponse): ScanResult {
  const state = normalizeState(response.state ?? response.status ?? response.result);

  if (state === 'success') {
    return {
      outcome: 'success',
      title: 'Checked In',
      message: response.message ?? 'Ticket verified successfully.',
      attendeeName: response.attendee_name,
      ticketType: response.ticket_type,
      checkedInAt: response.checked_in_at,
    };
  }

  if (state === 'already_used') {
    return {
      outcome: 'already_used',
      title: 'Already Used',
      message: response.message ?? 'This ticket was already checked in.',
      attendeeName: response.attendee_name,
      ticketType: response.ticket_type,
      checkedInAt: response.checked_in_at,
    };
  }

  if (state === 'wrong_event') {
    return {
      outcome: 'wrong_event',
      title: 'Wrong Event',
      message: response.message ?? 'This ticket belongs to a different event.',
    };
  }

  return {
    outcome: 'invalid',
    title: 'Invalid Ticket',
    message: response.message ?? 'Ticket could not be verified.',
  };
}

export function mapScanErrorToResult(error: unknown): ScanResult {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return {
        outcome: 'unauthorized',
        title: 'Not Authorized',
        message: 'You do not have access to scanner mode for this event.',
      };
    }

    if (error.status === 409) {
      return {
        outcome: 'already_used',
        title: 'Already Used',
        message: error.message || 'This ticket has already been used.',
      };
    }

    if (error.status === 404 || error.status === 422) {
      return {
        outcome: 'invalid',
        title: 'Invalid Ticket',
        message: error.message || 'Ticket could not be validated.',
      };
    }

    return {
      outcome: 'server_error',
      title: 'Scan Failed',
      message: error.message || 'Server error while checking in this ticket.',
    };
  }

  if (error instanceof TypeError) {
    return {
      outcome: 'network_error',
      title: 'Network Error',
      message: 'Unable to reach server. Check your connection and try again.',
    };
  }

  return {
    outcome: 'server_error',
    title: 'Scan Failed',
    message: 'Something went wrong while processing this scan.',
  };
}

export function formatCheckedInTime(value?: string) {
  if (!value) {
    return null;
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return value;
  }

  return parsedDate.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}
