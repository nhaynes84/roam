#!/usr/bin/env node

import { spawnSync } from 'node:child_process';

const ACTIONS = {
  3: {
    name: 'tmux-pane',
    tmux: { type: 'next-pane' },
    script: [
      'tell application "System Events"',
      '  keystroke "b" using control down',
      '  delay 0.05',
      '  keystroke "o"',
      'end tell',
    ],
  },
  4: {
    name: 'cycle-mode',
    tmux: { keys: ['BTab'] },
    script: [
      'tell application "System Events"',
      '  key code 48 using shift down',
      'end tell',
    ],
  },
  6: {
    name: 'approve-yes',
    tmux: { keys: ['y', 'Enter'] },
    script: [
      'tell application "System Events"',
      '  keystroke "y"',
      '  delay 0.03',
      '  key code 36',
      'end tell',
    ],
  },
  7: {
    name: 'approve-always',
    tmux: { keys: ['Tab', 'Enter'] },
    script: [
      'tell application "System Events"',
      '  key code 48',
      '  delay 0.03',
      '  key code 36',
      'end tell',
    ],
  },
  8: {
    name: 'escape',
    tmux: { keys: ['Escape'] },
    script: [
      'tell application "System Events"',
      '  key code 53',
      'end tell',
    ],
  },
  9: {
    name: 'kill-process',
    tmux: { keys: ['C-c'] },
    script: [
      'tell application "System Events"',
      '  keystroke "c" using control down',
      'end tell',
    ],
  },
  10: {
    name: 'enter',
    tmux: { keys: ['Enter'] },
    script: [
      'tell application "System Events"',
      '  key code 36',
      'end tell',
    ],
  },
};

const args = parseArgs(process.argv.slice(2));
const command = ACTIONS[args.actionId];

if (!command) {
  console.log(`ignored action=${args.actionId}`);
  process.exit(0);
}

if (args.dryRun) {
  const backend = resolveBackend(command, args.backend);
  console.log(`dry-run action=${args.actionId} name=${command.name} backend=${backend}`);
  process.exit(0);
}

const backend = resolveBackend(command, args.backend);

if (backend === 'tmux') {
  dispatchTmux(command);
} else {
  dispatchOsa(command);
}

console.log(`dispatched action=${args.actionId} name=${command.name} backend=${backend}`);

function parseArgs(argv) {
  const parsed = {
    actionId: null,
    backend: process.env.ROAM_COMMAND_BACKEND || 'auto',
    tmuxTarget: process.env.ROAM_TMUX_TARGET || '',
    dryRun: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--action-id') parsed.actionId = Number(argv[++i]);
    else if (arg === '--backend') parsed.backend = argv[++i] ?? parsed.backend;
    else if (arg === '--tmux-target') parsed.tmuxTarget = argv[++i] ?? '';
    else if (arg === '--dry-run') parsed.dryRun = true;
    else if (arg === '--help') usage();
    else throw new Error(`unknown arg: ${arg}`);
  }

  if (!Number.isInteger(parsed.actionId) || parsed.actionId < 0) {
    throw new Error(`invalid action-id: ${parsed.actionId}`);
  }
  if (!['auto', 'tmux', 'osascript'].includes(parsed.backend)) {
    throw new Error(`invalid backend: ${parsed.backend}`);
  }

  return parsed;
}

function usage() {
  console.log(
    'usage: roam-mac-command.mjs --action-id ACTION_ID ' +
    '[--backend auto|tmux|osascript] [--tmux-target TARGET] [--dry-run]',
  );
  process.exit(0);
}

function resolveBackend(command, requested) {
  if (requested === 'osascript') return 'osascript';
  if (requested === 'tmux') return 'tmux';
  return command.tmux && tmuxAvailable() ? 'tmux' : 'osascript';
}

function tmuxAvailable() {
  const result = spawnSync('tmux', ['display-message', '-p', '-t', tmuxTargetArg(), '#{session_name}:#{window_index}.#{pane_index}'], {
    encoding: 'utf8',
  });
  return result.status === 0;
}

function dispatchTmux(command) {
  if (!command.tmux) throw new Error(`no tmux mapping for ${command.name}`);

  if (command.tmux.type === 'next-pane') {
    selectNextTmuxPane();
    return;
  }

  const target = tmuxTargetArg();
  const result = spawnSync('tmux', ['send-keys', '-t', target, ...command.tmux.keys], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`tmux send-keys failed: ${detail}`);
  }
}

function selectNextTmuxPane() {
  const info = tmuxDisplay(['#{session_name}', '#{window_index}', '#{pane_index}'].join('\t'))
    .trim()
    .split('\t');
  if (info.length !== 3 || info.some((value) => value === '')) {
    throw new Error(`could not resolve tmux target: ${info.join(' ')}`);
  }

  const [session, windowIndex, paneIndex] = info;
  const windowTarget = `${session}:${windowIndex}`;
  const panes = tmuxListPanes(windowTarget);
  const currentOffset = panes.indexOf(Number(paneIndex));
  if (currentOffset < 0 || panes.length === 0) {
    throw new Error(`current pane ${paneIndex} not found in ${windowTarget}`);
  }

  const nextPane = panes[(currentOffset + 1) % panes.length];
  const result = spawnSync('tmux', ['select-pane', '-t', `${windowTarget}.${nextPane}`], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`tmux select-pane failed: ${detail}`);
  }
}

function tmuxDisplay(format) {
  const result = spawnSync('tmux', ['display-message', '-p', '-t', tmuxTargetArg(), format], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`tmux display-message failed: ${detail}`);
  }
  return result.stdout;
}

function tmuxListPanes(windowTarget) {
  const result = spawnSync('tmux', ['list-panes', '-t', windowTarget, '-F', '#{pane_index}'], {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`tmux list-panes failed: ${detail}`);
  }
  return result.stdout
    .trim()
    .split('\n')
    .map((line) => Number(line))
    .filter((value) => Number.isInteger(value))
    .sort((a, b) => a - b);
}

function tmuxTargetArg() {
  return args.tmuxTarget || ':';
}

function dispatchOsa(command) {
  const result = spawnSync('osascript', command.script.flatMap((line) => ['-e', line]), {
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`osascript failed: ${detail}`);
  }
}
