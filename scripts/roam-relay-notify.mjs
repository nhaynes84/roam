#!/usr/bin/env node

import fs from 'node:fs';
import net from 'node:net';

const FRAME_TEXT = 3;
const args = parseArgs(process.argv.slice(2));
const text = args.text.length > 0
  ? args.text.join(' ')
  : fs.readFileSync(0, 'utf8');

const normalized = text.replace(/\r\n/g, '\n').replace(/\s+/g, ' ').trim();
if (!normalized) process.exit(0);

const payload = Buffer.from(normalized, 'utf8');
if (payload.length > 0xffff) {
  throw new Error(`message too long for relay frame: ${payload.length} bytes`);
}

const header = Buffer.alloc(3);
header[0] = FRAME_TEXT;
header.writeUInt16BE(payload.length, 1);

const socket = net.createConnection({ host: args.host, port: args.port }, () => {
  socket.end(Buffer.concat([header, payload]));
});

socket.on('error', (error) => {
  console.error(`roam relay notify failed: ${error.message}`);
  process.exitCode = 1;
});

function parseArgs(argv) {
  const parsed = {
    host: '127.0.0.1',
    port: 8765,
    text: [],
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--host') parsed.host = argv[++i] ?? parsed.host;
    else if (arg === '--port') parsed.port = Number(argv[++i] ?? parsed.port);
    else if (arg === '--help') usage();
    else parsed.text.push(arg);
  }

  if (!Number.isInteger(parsed.port) || parsed.port < 1 || parsed.port > 65535) {
    throw new Error(`invalid port: ${parsed.port}`);
  }
  return parsed;
}

function usage() {
  console.log('usage: roam-relay-notify.mjs [--host 127.0.0.1] [--port 8765] [message...]');
  process.exit(0);
}
