/**
 * Sending through smoove.
 *
 * smoove is a marketing automation platform, not a transactional mail relay:
 * you do not hand it a subject and an HTML body over the API. The message
 * itself is built and stored in smoove, and the API's job is to say *who*
 * should receive it and *when*. Two shapes cover almost everything:
 *
 *   1. Triggered send — an automation in smoove is configured with an API
 *      trigger. You call the trigger with a contact, and smoove sends that
 *      contact the email defined in the automation. This is the transactional
 *      path: receipts, welcome mails, password links.
 *
 *   2. List send — a newsletter built in smoove goes out to a list. Adding a
 *      contact to a list is an API call; scheduling the newsletter is normally
 *      done in the smoove UI.
 *
 * Everything here is server side. See client.js for why that matters.
 */

import { SmooveClient, SmooveError } from './client.js';

/**
 * Path template for firing an API-triggered automation.
 *
 * UNVERIFIED — this is the one path in this module that was not confirmed
 * against a live account. Check it against your account's Swagger (Settings >
 * API Keys, "validate connection using Swagger") and correct it here if it
 * differs; nothing else in this module needs to change.
 *
 * Override without editing the file by setting SMOOVE_TRIGGER_PATH, using
 * {automationId} as the placeholder.
 */
const TRIGGER_PATH =
  process.env.SMOOVE_TRIGGER_PATH || '/Automations/{automationId}/Trigger';

/**
 * Fires an API-triggered automation for a single contact.
 *
 * Dry runs are the default. Sending mail in the organization's name is not
 * reversible, so the caller has to ask for it explicitly with `confirm: true`.
 * A dry run resolves the contact and reports what would happen without firing.
 */
export async function triggerAutomation({
  client = new SmooveClient(),
  automationId,
  email,
  fields = {},
  confirm = false,
} = {}) {
  if (!automationId) throw new TypeError('automationId is required');
  if (!email) throw new TypeError('email is required');

  const path = TRIGGER_PATH.replace('{automationId}', encodeURIComponent(automationId));

  if (!confirm) {
    return {
      sent: false,
      dryRun: true,
      wouldCall: `POST ${client.baseUrl}${path}`,
      recipient: email,
      fields,
    };
  }

  try {
    const result = await client.post(path, { email, ...fields });
    return { sent: true, dryRun: false, recipient: email, result };
  } catch (error) {
    if (error instanceof SmooveError && error.status === 404) {
      throw new SmooveError(
        `Automation trigger endpoint not found at ${path}. This path is the one ` +
          `part of the integration that was not verified against a live account. ` +
          `Open your account's Swagger, find the automation-trigger operation, and ` +
          `set SMOOVE_TRIGGER_PATH (or edit TRIGGER_PATH in smoove/send.js).`,
        { status: 404, method: 'POST', path },
      );
    }
    throw error;
  }
}

/**
 * Adds a contact to a list, which is how a recipient enters a newsletter's
 * audience. Upserts, so re-running with the same address is safe.
 */
export async function addContactToList({
  client = new SmooveClient(),
  listId,
  email,
  fields = {},
} = {}) {
  if (!listId) throw new TypeError('listId is required');
  if (!email) throw new TypeError('email is required');

  return client.upsertContact({
    email,
    ...fields,
    lists_ToSubscribe: [Number(listId)],
  });
}

/**
 * Confirms a key works and reports what it can see. Read-only, so it is the
 * safe first call when wiring up a new key or debugging a 401.
 */
export async function verifyKey({ client = new SmooveClient() } = {}) {
  const lists = await client.listLists();
  return {
    ok: true,
    baseUrl: client.baseUrl,
    listCount: Array.isArray(lists) ? lists.length : null,
    lists: Array.isArray(lists)
      ? lists.map((list) => ({ id: list.id, name: list.name }))
      : lists,
  };
}
