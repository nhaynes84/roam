#!/usr/bin/env node

import fs from 'node:fs';
import { spawnSync } from 'node:child_process';

const TMUX_TEXT_CHARS_PER_CHUNK = 800;

const args = parseArgs(process.argv.slice(2));
const text = fs.readFileSync(0, 'utf8').replace(/\r\n/g, '\n').trim();

if (!text) process.exit(0);

if (args.mode === 'clipboard') {
  pbcopy(text);
  console.log('copied transcript to clipboard');
  process.exit(0);
}

if (args.mode === 'tmux' || args.mode === 'tmux-submit') {
  sendTmuxText(text);
  if (args.mode === 'tmux-submit') sendTmuxKeys(['Enter']);
  console.log(`injected transcript mode=${args.mode} chars=${text.length}`);
  process.exit(0);
}

const previousClipboard = args.restoreClipboard ? pbpaste() : null;
pbcopy(text);

const script = [
  'tell application "System Events"',
  '  keystroke "v" using command down',
  `  delay ${args.delayMs / 1000}`,
];
if (args.mode === 'submit') script.push('  key code 36');
script.push('end tell');

const result = spawnSync('osascript', script.flatMap((line) => ['-e', line]), {
  encoding: 'utf8',
});
if (result.status !== 0) {
  const detail = (result.stderr || result.stdout || '').trim();
  throw new Error(`osascript failed: ${detail}`);
}

if (args.restoreClipboard && previousClipboard !== null) {
  await delay(args.restoreDelayMs);
  pbcopy(previousClipboard);
}

console.log(`injected transcript mode=${args.mode} chars=${text.length}`);

function parseArgs(argv) {
  const parsed = {
    mode: 'paste',
    tmuxTarget: process.env.ROAM_TMUX_TARGET || '',
    delayMs: 180,
    restoreClipboard: false,
    restoreDelayMs: 750,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--mode') parsed.mode = argv[++i] ?? parsed.mode;
    else if (arg === '--tmux-target') parsed.tmuxTarget = argv[++i] ?? '';
    else if (arg === '--delay-ms') parsed.delayMs = Number(argv[++i] ?? parsed.delayMs);
    else if (arg === '--restore-clipboard') parsed.restoreClipboard = true;
    else if (arg === '--restore-delay-ms') parsed.restoreDelayMs = Number(argv[++i] ?? parsed.restoreDelayMs);
    else if (arg === '--help') usage();
    else throw new Error(`unknown arg: ${arg}`);
  }

  if (!['clipboard', 'paste', 'submit', 'tmux', 'tmux-submit'].includes(parsed.mode)) {
    throw new Error(`invalid mode: ${parsed.mode}`);
  }
  if (!Number.isFinite(parsed.delayMs) || parsed.delayMs < 0) {
    throw new Error(`invalid delay-ms: ${parsed.delayMs}`);
  }
  if (!Number.isFinite(parsed.restoreDelayMs) || parsed.restoreDelayMs < 0) {
    throw new Error(`invalid restore-delay-ms: ${parsed.restoreDelayMs}`);
  }

  return parsed;
}

function usage() {
  console.log(
    'usage: roam-input-injector.mjs ' +
    '[--mode clipboard|paste|submit|tmux|tmux-submit] [--tmux-target TARGET] < transcript.txt',
  );
  process.exit(0);
}

function pbcopy(value) {
  const result = spawnSync('pbcopy', [], {
    input: value,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`pbcopy failed: ${detail}`);
  }
}

function pbpaste() {
  const result = spawnSync('pbpaste', [], {
    encoding: 'utf8',
  });
  if (result.status !== 0) return '';
  return result.stdout;
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sendTmuxText(value) {
  for (const chunk of splitText(value, TMUX_TEXT_CHARS_PER_CHUNK)) {
    const result = spawnSync('tmux', ['send-keys', '-t', tmuxTargetArg(), '-l', chunk], {
      encoding: 'utf8',
    });
    if (result.status !== 0) {
      const detail = (result.stderr || result.stdout || '').trim();
      throw new Error(`tmux send-keys failed: ${detail}`);
    }
  }
}

function sendTmuxKeys(keys) {
  const result = spawnSync('tmux', ['send-keys', '-t', tmuxTargetArg(), ...keys], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`tmux send-keys failed: ${detail}`);
  }
}

function tmuxTargetArg() {
  return args.tmuxTarget || ':';
}

function splitText(value, maxChars) {
  const chunks = [];
  let current = '';
  for (const char of value) {
    if (current.length > 0 && current.length + char.length > maxChars) {
      chunks.push(current);
      current = '';
    }
    current += char;
  }
  if (current.length > 0) chunks.push(current);
  return chunks;
}
