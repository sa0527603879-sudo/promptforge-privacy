/**
 * Minimal server-side client for the smoove REST API.
 *
 * SERVER SIDE ONLY. The key this reads grants access to the organization's
 * contact lists and the ability to send in the organization's name. Importing
 * this from browser code, or bundling it into anything a browser downloads,
 * hands that access to anyone who opens devtools.
 *
 * The key is read from the SMOOVE_API_KEY environment variable and is never
 * written to disk, logged, or included in thrown errors.
 */

const DEFAULT_BASE_URL = 'https://rest.smoove.io/v1';
const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_MAX_RETRIES = 3;

/** Status codes worth retrying: rate limiting and transient upstream faults. */
const RETRYABLE = new Set([429, 500, 502, 503, 504]);

export class SmooveError extends Error {
  constructor(message, { status, body, method, path } = {}) {
    super(message);
    this.name = 'SmooveError';
    this.status = status;
    this.body = body;
    this.method = method;
    this.path = path;
  }
}

export class SmooveConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SmooveConfigError';
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Retry-After is either a delay in seconds or an HTTP date. Returns null when
 * the header is absent or unparseable, letting the caller fall back to backoff.
 */
function retryAfterMs(response) {
  const header = response.headers.get('retry-after');
  if (!header) return null;

  const seconds = Number(header);
  if (Number.isFinite(seconds)) return seconds * 1000;

  const date = Date.parse(header);
  if (Number.isNaN(date)) return null;
  return Math.max(0, date - Date.now());
}

/** Exponential backoff with jitter, so parallel callers don't retry in lockstep. */
function backoffMs(attempt) {
  const base = 500 * 2 ** attempt;
  return base + Math.random() * base * 0.25;
}

export class SmooveClient {
  constructor({
    apiKey = process.env.SMOOVE_API_KEY,
    baseUrl = process.env.SMOOVE_BASE_URL || DEFAULT_BASE_URL,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    maxRetries = DEFAULT_MAX_RETRIES,
  } = {}) {
    if (!apiKey) {
      throw new SmooveConfigError(
        'SMOOVE_API_KEY is not set. Set it in the runtime environment ' +
          '(Netlify site environment variables, Supabase function secrets, or a ' +
          'local .env that is gitignored). Do not hardcode it.',
      );
    }

    this.#apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.timeoutMs = timeoutMs;
    this.maxRetries = maxRetries;
  }

  #apiKey;

  /**
   * Issues a request against the smoove API, retrying transient failures.
   *
   * `path` is appended to the base URL, so any endpoint is reachable through
   * this method — the named helpers below are conveniences, not a whitelist.
   */
  async request(method, path, { query, body } = {}) {
    const url = new URL(this.baseUrl + path);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }

    const headers = {
      Authorization: `Bearer ${this.#apiKey}`,
      Accept: 'application/json',
    };
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    let lastError;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0) await sleep(lastError?.retryDelay ?? backoffMs(attempt - 1));

      let response;
      try {
        response = await fetch(url, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: AbortSignal.timeout(this.timeoutMs),
        });
      } catch (cause) {
        // Network-level failure: DNS, TLS, timeout, or a blocked egress proxy.
        lastError = new SmooveError(
          `${method} ${path} failed to reach ${this.baseUrl}: ${cause.message}`,
          { method, path },
        );
        lastError.cause = cause;
        continue;
      }

      const payload = await this.#readBody(response);

      if (response.ok) return payload;

      if (RETRYABLE.has(response.status) && attempt < this.maxRetries) {
        lastError = new SmooveError(
          `${method} ${path} returned ${response.status}`,
          { status: response.status, body: payload, method, path },
        );
        lastError.retryDelay = retryAfterMs(response) ?? backoffMs(attempt);
        continue;
      }

      throw new SmooveError(
        this.#describeFailure(response.status, method, path, payload),
        { status: response.status, body: payload, method, path },
      );
    }

    throw lastError;
  }

  async #readBody(response) {
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  #describeFailure(status, method, path, payload) {
    const detail =
      typeof payload === 'string'
        ? payload.slice(0, 500)
        : JSON.stringify(payload)?.slice(0, 500);

    // A 403 can come from an egress proxy that never let the request out,
    // which looks nothing like a rejected key. Say which one it was.
    if (/not in allowlist|egress|blocked by .*proxy/i.test(detail ?? '')) {
      return (
        `${method} ${path} never reached ${this.baseUrl} — the network blocked it ` +
        `before it left. Allow the host in the environment's network settings. ` +
        `Detail: ${detail}`
      );
    }

    if (status === 401 || status === 403) {
      return (
        `${method} ${path} returned ${status}. The key was rejected, or it lacks ` +
        `the permission level this endpoint needs, or the account restricts the ` +
        `key to a different IP address. Detail: ${detail}`
      );
    }
    return `${method} ${path} returned ${status}. Detail: ${detail}`;
  }

  get(path, options) {
    return this.request('GET', path, options);
  }

  post(path, body, options) {
    return this.request('POST', path, { ...options, body });
  }

  put(path, body, options) {
    return this.request('PUT', path, { ...options, body });
  }

  delete(path, options) {
    return this.request('DELETE', path, options);
  }

  /** Cheapest authenticated read — use it to confirm a key works. */
  listLists() {
    return this.get('/Lists');
  }

  createList(list) {
    return this.post('/Lists', list);
  }

  /**
   * Creates a contact, or updates it when the email already exists.
   * `updateIfExists` is what makes this an upsert rather than a 409.
   */
  upsertContact(contact, { restoreDeleted = false } = {}) {
    return this.post('/Contacts', contact, {
      query: { updateIfExists: true, restoreDeleted },
    });
  }

  getContactByEmail(email) {
    return this.get(`/Contacts/${encodeURIComponent(email)}`, {
      query: { by: 'email' },
    });
  }
}
