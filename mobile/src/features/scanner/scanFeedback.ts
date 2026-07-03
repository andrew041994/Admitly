import { ApiError } from '../../api/client';

export type ScanUiState = 'requesting_permission' | 'permission_denied' | 'ready' | 'processing' | 'success' | 'error';

export type ScanOutcome =
  | 'success'
  | 'already_used'
  | 'invalid'
  | 'ticket_not_found'
  | 'wrong_event'
  | 'expired'
  | 'validation_failed'
  | 'unauthorized'
  | 'unable_to_scan'
  | 'camera_error'
  | 'network_error'
  | 'server_error'
  | 'unexpected_error';

export type ScanResultTone = 'success' | 'warning' | 'error' | 'unable';

export type ScanResult = {
  outcome: ScanOutcome;
  title: string;
  message: string;
  attendeeName?: string;
  ticketType?: string;
  checkedInAt?: string;
  eventTitle?: string;
};

export type ScanApiSuccessResponse = {
  success?: boolean;
  code?: string;
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

export function buildScanResultFromSuccessResponse(response: ScanApiSuccessResponse, eventTitle?: string): ScanResult {
  const state = normalizeState(response.state ?? response.status ?? response.result ?? response.code);

  if (response.success || state === 'success' || state === 'admitted') {
    return {
      outcome: 'success',
      title: 'Checked In',
      message: response.message ?? 'Ticket verified successfully.',
      attendeeName: response.attendee_name,
      ticketType: response.ticket_type,
      checkedInAt: response.checked_in_at,
      eventTitle,
    };
  }

  if (state === 'already_used' || state === 'checked_in' || state === 'already_checked_in') {
    return {
      outcome: 'already_used',
      title: 'Already Used',
      message: response.message ?? 'This ticket was already checked in.',
      attendeeName: response.attendee_name,
      ticketType: response.ticket_type,
      checkedInAt: response.checked_in_at,
      eventTitle,
    };
  }

  if (state === 'wrong_event') {
    return {
      outcome: 'wrong_event',
      title: 'Wrong Event',
      message: response.message ?? 'This ticket belongs to a different event.',
      eventTitle,
    };
  }

  if (state === 'expired' || state === 'ticket_expired') {
    return {
      outcome: 'expired',
      title: 'Expired Ticket',
      message: response.message ?? 'This ticket is expired and cannot be checked in.',
      eventTitle,
    };
  }

  if (state === 'not_found' || state === 'ticket_not_found') {
    return {
      outcome: 'ticket_not_found',
      title: 'Ticket Not Found',
      message: response.message ?? 'We could not find a ticket for this QR code.',
      eventTitle,
    };
  }

  if (state === 'validation_failed' || state === 'failed_validation') {
    return {
      outcome: 'validation_failed',
      title: 'Validation Failed',
      message: response.message ?? 'This ticket could not be validated for entry.',
      eventTitle,
    };
  }

  return {
    outcome: 'invalid',
    title: 'Invalid Ticket',
    message: response.message ?? 'Ticket could not be verified.',
    eventTitle,
  };
}

export const mapScanResponseToResult = buildScanResultFromSuccessResponse;

export function buildScanResultFromApiError(error: unknown, eventTitle?: string): ScanResult {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      return {
        outcome: 'unauthorized',
        title: 'Not Authorized',
        message: error.message || 'You do not have access to scanner mode for this event.',
        eventTitle,
      };
    }

    if (error.status === 409) {
      return {
        outcome: 'already_used',
        title: 'Already Used',
        message: error.message || 'This ticket has already been used.',
        eventTitle,
      };
    }

    if (error.status === 404) {
      return {
        outcome: 'ticket_not_found',
        title: 'Ticket Not Found',
        message: error.message || 'We could not find a ticket for this QR code.',
        eventTitle,
      };
    }

    if (error.status === 422) {
      return {
        outcome: 'validation_failed',
        title: 'Validation Failed',
        message: error.message || 'Ticket could not be validated.',
        eventTitle,
      };
    }

    return {
      outcome: 'server_error',
      title: 'Scan Failed',
      message: error.message || 'Server error while checking in this ticket.',
      eventTitle,
    };
  }

  if (error instanceof TypeError) {
    return {
      outcome: 'network_error',
      title: 'Network Error',
      message: 'Unable to reach server. Check your connection and try again.',
      eventTitle,
    };
  }

  return {
    outcome: 'server_error',
    title: 'Scan Failed',
    message: 'Something went wrong while processing this scan.',
  };
}

export const mapScanErrorToResult = buildScanResultFromApiError;

export function buildScanResultFromUnexpectedError(message = 'Something went wrong while processing this scan.', eventTitle?: string): ScanResult {
  return {
    outcome: 'unexpected_error',
    title: 'Scan Failed',
    message,
    eventTitle,
  };
}

export function getScanResultTone(result: ScanResult): ScanResultTone {
  if (result.outcome === 'success') return 'success';
  if (result.outcome === 'already_used' || result.outcome === 'wrong_event' || result.outcome === 'expired') return 'warning';
  if (result.outcome === 'unable_to_scan' || result.outcome === 'camera_error' || result.outcome === 'network_error') return 'unable';
  return 'error';
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
