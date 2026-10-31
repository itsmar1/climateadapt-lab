/**
 * API error contract. Every backend failure arrives as
 * `{ detail: [{ loc, msg, type }] }`; `type` is the stable machine code and
 * this module maps each known code to one specific user-facing message.
 * Unknown codes fall back to a generic message that still names the code.
 */

export const ERROR_MESSAGES: Record<string, string> = {
  outside_coverage:
    'This location is outside the dataset coverage. Try a point inside the hinted ranges.',
  data_not_available:
    'No observations exist for the requested window. Try an earlier target month.',
  missing_data:
    'Some required values are missing for this window, so the value was not computed.',
  insufficient_baseline:
    'Too few complete baseline years exist for this point and window.',
  insufficient_reference:
    'Too few complete reference years exist for this point and window.',
  download_error:
    'A source archive request failed. Wait a little and retry.',
  data_integrity_error:
    'A downloaded source file failed its integrity check. Retry later.',
  job_not_found: 'This job is unknown or has expired. Create a new scenario.',
  timeout: 'The job exceeded its time budget. Retry with a smaller request.',
  internal: 'Something went wrong on the server. Retry; the detail was logged.',
  server_busy: 'The server is at capacity. Wait a few seconds and retry.',
  scenario_not_found: 'This scenario is unknown or was deleted.',
  request_too_large: 'The request body is too large. Shorten the inputs and retry.',
  'network-error': 'The backend could not be reached. Is it running?',
  'request-timeout': 'The request timed out. Check the backend and retry.',
  'unsupported-version':
    'The backend answered with an unknown contract version. Update the app.',
};

export function messageForCode(code: string): string {
  return ERROR_MESSAGES[code] ?? `The request failed (${code}).`;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  /** Raw parsed body (present for detail-shaped failures; used for 422 fields). */
  readonly body: unknown;

  constructor(code: string, status: number, message?: string, body?: unknown) {
    super(message ?? messageForCode(code));
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.body = body;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

interface DetailItem {
  loc: unknown;
  msg: unknown;
  type: unknown;
}

function firstDetail(body: unknown): DetailItem | null {
  if (!isRecord(body) || !Array.isArray(body.detail) || body.detail.length === 0) {
    return null;
  }
  const item = body.detail[0];
  if (!isRecord(item)) {
    return null;
  }
  return { loc: item.loc, msg: item.msg, type: item.type };
}

/** Build an ApiError from an HTTP status plus a parsed (or missing) body. */
export function parseApiError(status: number, body: unknown): ApiError {
  const detail = firstDetail(body);
  if (detail && typeof detail.type === 'string' && detail.type.length > 0) {
    return new ApiError(detail.type, status, undefined, body);
  }
  return new ApiError('internal', status, undefined, body);
}

/**
 * Extract per-field messages from a 422 validation body (`loc` looks like
 * `["body", "<field>"]`). Never echoes the rejected input values.
 */
export function parseValidationErrors(body: unknown): Record<string, string> {
  const fields: Record<string, string> = {};
  if (!isRecord(body) || !Array.isArray(body.detail)) {
    return fields;
  }
  for (const item of body.detail) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') {
      continue;
    }
    const field = item.loc.length > 0 ? item.loc[item.loc.length - 1] : undefined;
    if (typeof field === 'string' && field.length > 0 && !(field in fields)) {
      fields[field] = item.msg;
    }
  }
  return fields;
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (isRecord(error) && error.name === 'AbortError')
  );
}
