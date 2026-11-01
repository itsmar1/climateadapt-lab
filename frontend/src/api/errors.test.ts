import { describe, expect, it } from 'vitest';
import {
  ERROR_MESSAGES,
  messageForCode,
  parseApiError,
  parseValidationErrors,
} from './errors';

describe('error code messages', () => {
  it('maps every known backend code to a specific non-empty message', () => {
    const codes = [
      'outside_coverage',
      'data_not_available',
      'missing_data',
      'insufficient_baseline',
      'insufficient_reference',
      'download_error',
      'data_integrity_error',
      'job_not_found',
      'timeout',
      'internal',
      'server_busy',
      'scenario_not_found',
      'request_too_large',
      'demo_mode_disabled',
      'demo_snapshot_not_found',
    ];
    for (const code of codes) {
      const message = messageForCode(code);
      expect(message.length, code).toBeGreaterThan(20);
      expect(message, code).not.toContain(code);
    }
    const unique = new Set(codes.map(messageForCode));
    expect(unique.size).toBe(codes.length);
  });

  it('falls back to a generic message that names an unknown code', () => {
    expect(messageForCode('future_code')).toContain('future_code');
    expect(ERROR_MESSAGES['future_code']).toBeUndefined();
  });
});

describe('parseApiError', () => {
  it('keeps the backend type code and status', () => {
    const error = parseApiError(404, {
      detail: [{ loc: [], msg: 'Unknown scenario id.', type: 'scenario_not_found' }],
    });
    expect(error.code).toBe('scenario_not_found');
    expect(error.status).toBe(404);
    expect(error.message).toBe(messageForCode('scenario_not_found'));
  });

  it('degrades gracefully on unshaped bodies', () => {
    expect(parseApiError(500, null).code).toBe('internal');
    expect(parseApiError(500, { detail: [] }).code).toBe('internal');
    expect(parseApiError(500, { detail: [{ type: 42 }] }).code).toBe('internal');
  });
});

describe('parseValidationErrors', () => {
  it('maps 422 loc paths to field messages without echoing input', () => {
    const fields = parseValidationErrors({
      detail: [
        { loc: ['body', 'latitude'], msg: 'field required', type: 'missing' },
        { loc: ['body', 'query'], msg: 'too long', type: 'string_too_long' },
      ],
    });
    expect(fields).toEqual({ latitude: 'field required', query: 'too long' });
  });

  it('ignores malformed items', () => {
    expect(parseValidationErrors(null)).toEqual({});
    expect(parseValidationErrors({ detail: [{ loc: [], msg: 'x' }] })).toEqual({});
    expect(parseValidationErrors({ detail: [{ loc: ['body', 3], msg: 'x' }] })).toEqual({});
  });
});
