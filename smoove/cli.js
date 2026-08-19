#!/usr/bin/env node
/**
 * Command line entry point for the smoove integration.
 *
 *   node smoove/cli.js verify
 *   node smoove/cli.js lists
 *   node smoove/cli.js subscribe --list 123 --email a@b.com --field firstName=Dana
 *   node smoove/cli.js trigger --automation 456 --email a@b.com --yes
 *
 * Reads SMOOVE_API_KEY from the environment. It never takes the key as an
 * argument: command lines end up in shell history and in the process list,
 * where other users on the machine can read them.
 */

import { parseArgs } from 'node:util';
import { SmooveClient, SmooveConfigError, SmooveError } from './client.js';
import { addContactToList, triggerAutomation, verifyKey } from './send.js';

const USAGE = `
Usage: node smoove/cli.js <command> [options]

Commands:
  verify                      Confirm SMOOVE_API_KEY works and show what it can see
  lists                       Print the account's lists
  subscribe                   Add or update a contact on a list
  trigger                     Fire an API-triggered automation for one contact

Options:
  --list <id>                 List id            (subscribe)
  --automation <id>           Automation id      (trigger)
  --email <address>           Contact email      (subscribe, trigger)
  --field <key=value>         Extra contact field, repeatable
  --yes                       Actually send. Without it, trigger is a dry run
  --json                      Print raw JSON instead of a summary
  --help                      Show this message
`.trim();

function parseFields(values = []) {
  return Object.fromEntries(
    values.map((pair) => {
      const index = pair.indexOf('=');
      if (index === -1) {
        throw new TypeError(`--field expects key=value, got "${pair}"`);
      }
      return [pair.slice(0, index), pair.slice(index + 1)];
    }),
  );
}

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      list: { type: 'string' },
      automation: { type: 'string' },
      email: { type: 'string' },
      field: { type: 'string', multiple: true, default: [] },
      yes: { type: 'boolean', default: false },
      json: { type: 'boolean', default: false },
      help: { type: 'boolean', default: false },
    },
  });

  const [command] = positionals;

  if (values.help || !command) {
    console.log(USAGE);
    return;
  }

  const client = new SmooveClient();
  const fields = parseFields(values.field);
  const print = (result, summary) =>
    console.log(values.json ? JSON.stringify(result, null, 2) : summary(result));

  switch (command) {
    case 'verify': {
      const result = await verifyKey({ client });
      print(result, (r) => `Key works against ${r.baseUrl}. ${r.listCount} list(s) visible.`);
      return;
    }

    case 'lists': {
      const lists = await client.listLists();
      print(lists, (r) =>
        (Array.isArray(r) ? r : [])
          .map((list) => `${list.id}\t${list.name}`)
          .join('\n') || 'No lists.',
      );
      return;
    }

    case 'subscribe': {
      const result = await addContactToList({
        client,
        listId: values.list,
        email: values.email,
        fields,
      });
      print(result, () => `Subscribed ${values.email} to list ${values.list}.`);
      return;
    }

    case 'trigger': {
      const result = await triggerAutomation({
        client,
        automationId: values.automation,
        email: values.email,
        fields,
        confirm: values.yes,
      });
      print(result, (r) =>
        r.dryRun
          ? `Dry run. Would call ${r.wouldCall} for ${r.recipient}.\n` +
            `Re-run with --yes to actually send.`
          : `Triggered automation ${values.automation} for ${r.recipient}.`,
      );
      return;
    }

    default:
      console.error(`Unknown command "${command}".\n\n${USAGE}`);
      process.exitCode = 1;
  }
}

main().catch((error) => {
  if (error instanceof SmooveConfigError) {
    console.error(`Configuration error: ${error.message}`);
  } else if (error instanceof SmooveError) {
    console.error(`smoove API error: ${error.message}`);
  } else {
    console.error(error.message);
  }
  process.exitCode = 1;
});
