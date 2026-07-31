#!/usr/bin/env node

import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const IMA_STEP_TABLE = [
  7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
  19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
  50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
  130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
  337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
  876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
  2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
  5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
  15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
];

const IMA_INDEX_TABLE = [
  -1, -1, -1, -1, 2, 4, 6, 8,
  -1, -1, -1, -1, 2, 4, 6, 8,
];

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_LOG_DIR = path.join(os.homedir(), 'Library', 'Logs', 'Roam');

const FRAME_EVENT = 1;
const FRAME_AUDIO = 2;
const FRAME_TEXT = 3;

const EVENT_ACTION = 1;
const EVENT_PTT_START = 2;
const EVENT_PTT_STOP = 3;
const EVENT_STATUS = 4;

const ACTION_DICTATION = 1;
const ACTION_DICTATION_ANDROID = 2;
const LOCAL_DISPLAY_ACTIONS = new Set([
  13, // LED toggle
  14, // profile toggle
  15, // scroll forward/newer
  16, // scroll back/older
  17, // clear messages
]);
const ACTION_NAMES = {
  3: 'Pane switch',
  4: 'Cycle mode',
  6: 'Approve',
  7: 'Always',
  8: 'Escape',
  9: 'Cancel',
  10: 'Enter',
};
const FEEDBACK_SCREEN_CHARS = 58;
const FEEDBACK_PAGE_PREFIX_CHARS = 6; // "1/9: "
const FEEDBACK_MAX_PAGES = 8;
const FEEDBACK_CONTINUE_TEXT = 'Ask continue for more.';
const FEEDBACK_FRAME_DELAY_MS = 350;
const NOTICE_REPLAY_WINDOW_MS = 120000;
const NOTICE_REPLAY_DELAY_MS = 1000;

const args = parseArgs(process.argv.slice(2));
let wavSink = null;
let transcriptionQueue = Promise.resolve();
const clients = new Map();
let lastManualNotice = null;

let clientCount = 0;
const server = net.createServer((socket) => {
  clientCount += 1;
  const clientId = clientCount;
  const state = {
    id: clientId,
    buffer: Buffer.alloc(0),
    lastSeq: null,
    frames: 0,
    audioBytes: 0,
    pcmSamples: 0,
    session: null,
    socket,
    remoteAddress: socket.remoteAddress || '',
    feedbackQueue: Promise.resolve(),
  };
  clients.set(clientId, state);

  console.log(`client ${clientId}: connected from ${socket.remoteAddress}:${socket.remotePort}`);
  sendRelayText(state, 'Relay linked');
  replayRecentNoticeOnReady(state);

  socket.on('data', (chunk) => {
    state.buffer = Buffer.concat([state.buffer, chunk]);
    drainFrames(clientId, state);
  });

  socket.on('close', () => {
    finishSessionCapture(clientId, state, null, 'socket-close');
    clients.delete(clientId);
    console.log(`client ${clientId}: closed`);
  });

  socket.on('error', (error) => {
    console.error(`client ${clientId}: ${error.message}`);
  });
});

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

function drainFrames(clientId, state) {
  while (state.buffer.length >= 3) {
    const type = state.buffer[0];
    const length = state.buffer.readUInt16BE(1);
    if (state.buffer.length < length + 3) return;

    const payload = state.buffer.subarray(3, 3 + length);
    state.buffer = state.buffer.subarray(3 + length);

    if (type === FRAME_EVENT) {
      handleEvent(clientId, state, payload);
    } else if (type === FRAME_AUDIO) {
      handleAudio(clientId, state, payload);
    } else if (type === FRAME_TEXT) {
      handleRelayText(clientId, payload);
    } else {
      console.warn(`client ${clientId}: unknown frame type ${type} (${length} bytes)`);
    }
  }
}

function handleEvent(clientId, state, payload) {
  const raw = payload.toString('utf8');
  try {
    const event = JSON.parse(raw);
    if (event.eventType === EVENT_PTT_START) {
      resetAudioState(state);
      startSessionCapture(clientId, state, event);
    } else if (event.eventType === EVENT_PTT_STOP) {
      finishSessionCapture(clientId, state, event, 'ptt-stop');
    } else if (event.eventType === EVENT_ACTION) {
      dispatchActionEvent(clientId, event);
    } else if (event.eventType === EVENT_STATUS) {
      if (!replayRecentNoticeOnReady(state)) {
        sendRelayText(state, 'Roam ready');
      }
    }
    console.log(`client ${clientId}: event ${JSON.stringify(event)}`);
  } catch {
    console.warn(`client ${clientId}: invalid event JSON: ${raw}`);
  }
}

function handleRelayText(clientId, payload) {
  const text = normalizeFeedbackText(payload.toString('utf8'));
  if (!text) return;
  console.log(`client ${clientId}: relay text ${JSON.stringify(text)}`);
  const state = clients.get(clientId);
  if (isLoopbackAddress(state?.remoteAddress || '')) {
    lastManualNotice = {
      text,
      ts: Date.now(),
      replayCount: 0,
      deliveredClientIds: new Set(),
    };
  }
  broadcastRelayText(text, {
    excludeClientId: clientId,
    deliveredClientIds: lastManualNotice?.text === text ? lastManualNotice.deliveredClientIds : null,
  });
}

function resetAudioState(state) {
  state.lastSeq = null;
  state.frames = 0;
  state.audioBytes = 0;
  state.pcmSamples = 0;
}

function dispatchActionEvent(clientId, event) {
  if (!args.commands) return;
  if (event.actionId === ACTION_DICTATION || event.actionId === ACTION_DICTATION_ANDROID) return;
  if (LOCAL_DISPLAY_ACTIONS.has(event.actionId)) return;

  const state = clients.get(clientId);
  runCommand(args.commandDispatcher, ['--action-id', String(event.actionId)], {
    timeoutMs: args.commandTimeoutSeconds * 1000,
  }).then(({ stdout, stderr }) => {
    const line = `${stdout}${stderr}`.trim();
    if (line) console.log(`client ${clientId}: command ${line}`);
    if (line.startsWith('ignored action=')) return;
    sendRelayText(state, ACTION_NAMES[event.actionId] || `Action ${event.actionId}`);
  }).catch((error) => {
    console.error(`client ${clientId}: command dispatch failed: ${error.message}`);
    sendRelayText(state, 'Command failed');
  });
}

function startSessionCapture(clientId, state, event) {
  if (!args.transcribe) return;
  if (state.session) finishSessionCapture(clientId, state, event, 'new-ptt-start');

  fs.mkdirSync(args.sessionDir, { recursive: true });
  const id = `${timestampForFile(new Date())}-client${clientId}-roam${event.roamMillis ?? 'na'}`;
  const wavPath = path.join(args.sessionDir, `${id}.wav`);

  state.session = {
    id,
    wavPath,
    sink: new WavSink(wavPath),
    startedAt: Date.now(),
    pcmBytes: 0,
    pcmSamples: 0,
  };
  console.log(`client ${clientId}: capture started ${wavPath}`);
  sendRelayText(state, 'Listening');
}

function writeSessionAudio(state, pcm) {
  if (!state.session || !pcm || pcm.length === 0) return;
  state.session.sink.write(pcm);
  state.session.pcmBytes += pcm.length;
  state.session.pcmSamples += pcm.length / 2;
}

function finishSessionCapture(clientId, state, event, reason) {
  if (!state.session) return;

  const session = state.session;
  state.session = null;
  session.endedAt = Date.now();
  session.reason = reason;
  session.endRoamMillis = event?.roamMillis ?? null;
  session.durationSeconds = session.pcmSamples / 16000;
  session.sink.close();

  console.log(
    `client ${clientId}: capture finished ${session.wavPath} ` +
    `seconds=${session.durationSeconds.toFixed(2)} reason=${reason}`,
  );
  sendRelayText(state, 'Transcribing');

  transcriptionQueue = transcriptionQueue
    .then(() => transcribeSession(clientId, session))
    .catch((error) => {
      console.error(`client ${clientId}: transcription failed: ${error.message}`);
      sendRelayText(clients.get(clientId), 'STT failed');
    });
}

async function transcribeSession(clientId, session) {
  const state = clients.get(clientId);
  if (session.durationSeconds < args.minSessionSeconds) {
    console.log(
      `client ${clientId}: transcription skipped short session ` +
      `seconds=${session.durationSeconds.toFixed(2)}`,
    );
    sendRelayText(state, 'Too short');
    return;
  }

  fs.mkdirSync(args.transcriptDir, { recursive: true });
  const outputName = path.basename(session.wavPath, '.wav');
  const jsonTranscriptPath = path.join(args.transcriptDir, `${outputName}.json`);
  const txtTranscriptPath = path.join(args.transcriptDir, `${outputName}.txt`);
  const sttArgs = [
    session.wavPath,
    '--model', args.sttModel,
    '--output-dir', args.transcriptDir,
    '--output-format', 'json',
    '--output-name', outputName,
    '--verbose', 'False',
    '--condition-on-previous-text', 'False',
  ];
  if (args.sttLanguage) sttArgs.push('--language', args.sttLanguage);

  console.log(`client ${clientId}: transcribing ${session.wavPath}`);
  const result = await runCommand(args.sttCommand, sttArgs, {
    timeoutMs: args.sttTimeoutSeconds * 1000,
  });

  const { text, transcriptPath } = readTranscriptOutput(jsonTranscriptPath, txtTranscriptPath);
  const record = {
    ts: new Date().toISOString(),
    clientId,
    wavPath: session.wavPath,
    transcriptPath,
    seconds: Number(session.durationSeconds.toFixed(3)),
    text,
    injected: false,
    injectMode: args.injectMode,
  };

  if (text.length < args.minTranscriptChars) {
    appendTranscriptRecord(record);
    const detail = `${result.stdout}${result.stderr}`.trim();
    if (!transcriptPath && detail) console.warn(`client ${clientId}: stt output without transcript: ${detail}`);
    console.log(`client ${clientId}: transcription skipped empty/short result`);
    sendRelayText(state, 'No speech');
    return;
  }

  console.log(`client ${clientId}: transcript ${JSON.stringify(text)}`);
  if (args.injectMode !== 'none') {
    try {
      await runCommand(process.execPath, [args.injector, '--mode', args.injectMode], {
        input: text,
        timeoutMs: args.injectTimeoutSeconds * 1000,
      });
      record.injected = true;
      console.log(`client ${clientId}: transcript injected mode=${args.injectMode}`);
      sendRelayText(state, args.injectMode.endsWith('submit') ? 'Sent' : 'Ready');
    } catch (error) {
      record.injectError = error.message;
      console.error(`client ${clientId}: transcript injection failed: ${error.message}`);
      sendRelayText(state, 'Send failed');
    }
  } else {
    sendRelayText(state, 'Transcribed');
  }

  appendTranscriptRecord(record);
}

function sendRelayText(state, text) {
  if (!state?.socket || !text) return;
  const pages = paginateFeedbackText(normalizeFeedbackText(text));
  const outbound = [...pages].reverse();

  state.feedbackQueue = (state.feedbackQueue || Promise.resolve())
    .catch(() => {})
    .then(async () => {
      for (const page of outbound) {
        if (!state.socket || state.socket.destroyed) return;
        sendRelayTextFrame(state, page);
        await sleep(FEEDBACK_FRAME_DELAY_MS);
      }
    });
}

function sendRelayTextFrame(state, text) {
  const payload = Buffer.from(text, 'utf8');
  if (payload.length === 0 || payload.length > 0xffff) return;

  const header = Buffer.alloc(3);
  header[0] = FRAME_TEXT;
  header.writeUInt16BE(payload.length, 1);
  console.log(`client ${state.id}: feedback ${JSON.stringify(text)}`);
  state.socket.write(Buffer.concat([header, payload]), (error) => {
    if (error) console.error(`client feedback failed: ${error.message}`);
  });
}

function broadcastRelayText(text, options = {}) {
  for (const [clientId, state] of clients.entries()) {
    if (clientId === options.excludeClientId) continue;
    sendRelayText(state, text);
    if (options.deliveredClientIds && !isLoopbackAddress(state.remoteAddress || '')) {
      options.deliveredClientIds.add(clientId);
    }
  }
}

function replayRecentNoticeOnReady(state) {
  if (!state || isLoopbackAddress(state.remoteAddress || '')) return false;
  if (!lastManualNotice) return false;
  if (Date.now() - lastManualNotice.ts > NOTICE_REPLAY_WINDOW_MS) return false;
  if (lastManualNotice.deliveredClientIds?.has(state.id)) return false;
  if (lastManualNotice.replayCount >= 2) return false;

  const text = lastManualNotice.text;
  lastManualNotice.deliveredClientIds?.add(state.id);
  lastManualNotice.replayCount += 1;
  setTimeout(() => {
    if (state.socket && !state.socket.destroyed) {
      sendRelayText(state, text);
    }
  }, NOTICE_REPLAY_DELAY_MS).unref();
  return true;
}

function isLoopbackAddress(address) {
  return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1';
}

function normalizeFeedbackText(raw) {
  return raw
    .replace(/\r\n/g, '\n')
    .replace(/\s+/g, ' ')
    .trim();
}

function paginateFeedbackText(text) {
  if (!text) return [];
  if (text.length <= FEEDBACK_SCREEN_CHARS) return [text];

  const bodyChars = FEEDBACK_SCREEN_CHARS - FEEDBACK_PAGE_PREFIX_CHARS;
  let bodies = splitTextForDisplay(text, bodyChars);
  if (bodies.length > FEEDBACK_MAX_PAGES) {
    bodies = bodies.slice(0, FEEDBACK_MAX_PAGES);
    bodies[FEEDBACK_MAX_PAGES - 1] = FEEDBACK_CONTINUE_TEXT;
  }

  const total = bodies.length;
  return bodies.map((body, index) => `${index + 1}/${total}: ${body}`);
}

function splitTextForDisplay(text, maxChars) {
  const pages = [];
  let remaining = text.trim();

  while (remaining.length > 0) {
    if (remaining.length <= maxChars) {
      pages.push(remaining);
      break;
    }

    let end = maxChars;
    while (end > Math.floor(maxChars * 0.55) && remaining[end] !== ' ') {
      end -= 1;
    }
    if (end <= Math.floor(maxChars * 0.55)) end = maxChars;

    pages.push(remaining.slice(0, end).trim());
    remaining = remaining.slice(end).trim();
  }

  return pages;
}

function appendTranscriptRecord(record) {
  fs.mkdirSync(path.dirname(args.transcriptLog), { recursive: true });
  fs.appendFileSync(args.transcriptLog, `${JSON.stringify(record)}\n`);
}

function readTranscriptOutput(jsonPath, txtPath) {
  if (fs.existsSync(jsonPath)) {
    const parsed = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
    return {
      text: normalizeTranscript(parsed.text || ''),
      transcriptPath: jsonPath,
    };
  }

  if (fs.existsSync(txtPath)) {
    return {
      text: normalizeTranscript(fs.readFileSync(txtPath, 'utf8')),
      transcriptPath: txtPath,
    };
  }

  return {
    text: '',
    transcriptPath: '',
  };
}

function normalizeTranscript(raw) {
  return raw
    .replace(/\[[^\]]*(music|applause|silence|noise|inaudible)[^\]]*\]/gi, ' ')
    .replace(/\([^)]*(music|applause|silence|noise|inaudible)[^)]*\)/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function handleAudio(clientId, state, packet) {
  if (packet.length < 12) {
    console.warn(`client ${clientId}: short audio packet (${packet.length} bytes)`);
    return;
  }

  const version = packet[0];
  const codec = packet[1];
  const seq = packet.readUInt16LE(2);
  const roamMillis = packet.readUInt32LE(4);
  const predictor = packet.readInt16LE(8);
  const stepIndex = packet[10];
  const flags = packet[11];
  const payload = packet.subarray(12);

  if (state.lastSeq !== null) {
    const expected = (state.lastSeq + 1) & 0xffff;
    if (seq !== expected) {
      const lost = (seq - expected + 0x10000) & 0xffff;
      console.warn(`client ${clientId}: audio gap expected=${expected} got=${seq} lost=${lost}`);
    }
  }
  state.lastSeq = seq;
  state.frames += 1;
  state.audioBytes += payload.length;

  if (version !== 1) {
    console.warn(`client ${clientId}: unsupported audio version ${version}`);
    return;
  }

  if (codec === 2) {
    const pcm = decodeImaAdpcm(payload, predictor, stepIndex);
    state.pcmSamples += pcm.length / 2;
    if (wavSink) wavSink.write(pcm);
    writeSessionAudio(state, pcm);
  } else if (codec === 1) {
    state.pcmSamples += payload.length / 2;
    if (wavSink) wavSink.write(payload);
    writeSessionAudio(state, payload);
  } else {
    console.warn(`client ${clientId}: unsupported codec ${codec}`);
    return;
  }

  if (state.frames === 1 || state.frames % 25 === 0) {
    console.log(
      `client ${clientId}: audio seq=${seq} ms=${roamMillis} codec=${codec} flags=${flags} ` +
      `frames=${state.frames} bytes=${state.audioBytes} samples=${state.pcmSamples}`,
    );
  }
}

function decodeImaAdpcm(payload, predictorStart, stepIndexStart) {
  let predictor = predictorStart;
  let stepIndex = Math.max(0, Math.min(88, stepIndexStart));
  const pcm = Buffer.alloc(payload.length * 4);
  let offset = 0;

  for (const byte of payload) {
    offset = decodeNibble(byte & 0x0f, pcm, offset);
    offset = decodeNibble((byte >> 4) & 0x0f, pcm, offset);
  }

  return pcm.subarray(0, offset);

  function decodeNibble(code, out, outOffset) {
    const step = IMA_STEP_TABLE[stepIndex];
    let delta = step >> 3;
    if (code & 4) delta += step;
    if (code & 2) delta += step >> 1;
    if (code & 1) delta += step >> 2;

    predictor = code & 8 ? predictor - delta : predictor + delta;
    predictor = Math.max(-32768, Math.min(32767, predictor));

    stepIndex += IMA_INDEX_TABLE[code & 0x0f];
    stepIndex = Math.max(0, Math.min(88, stepIndex));

    out.writeInt16LE(predictor, outOffset);
    return outOffset + 2;
  }
}

function parseArgs(argv) {
  const parsed = {
    host: '0.0.0.0',
    port: 8765,
    wav: '',
    transcribe: false,
    sessionDir: '',
    transcriptDir: '',
    transcriptLog: '',
    sttCommand: 'mlx_whisper',
    sttModel: 'mlx-community/whisper-large-v3-turbo',
    sttLanguage: 'en',
    sttTimeoutSeconds: 120,
    minSessionSeconds: 0.5,
    minTranscriptChars: 2,
    injectMode: 'none',
    injector: path.join(SCRIPT_DIR, 'roam-input-injector.mjs'),
    injectTimeoutSeconds: 10,
    commands: false,
    commandDispatcher: path.join(SCRIPT_DIR, 'roam-mac-command.mjs'),
    commandTimeoutSeconds: 5,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--host') parsed.host = argv[++i] ?? parsed.host;
    else if (arg === '--port') parsed.port = Number(argv[++i] ?? parsed.port);
    else if (arg === '--wav') parsed.wav = argv[++i] ?? '';
    else if (arg === '--transcribe') parsed.transcribe = true;
    else if (arg === '--no-transcribe') parsed.transcribe = false;
    else if (arg === '--session-dir') parsed.sessionDir = argv[++i] ?? '';
    else if (arg === '--transcript-dir') parsed.transcriptDir = argv[++i] ?? '';
    else if (arg === '--transcript-log') parsed.transcriptLog = argv[++i] ?? '';
    else if (arg === '--stt-command') parsed.sttCommand = argv[++i] ?? parsed.sttCommand;
    else if (arg === '--stt-model') parsed.sttModel = argv[++i] ?? parsed.sttModel;
    else if (arg === '--stt-language') parsed.sttLanguage = argv[++i] ?? '';
    else if (arg === '--stt-timeout-seconds') parsed.sttTimeoutSeconds = Number(argv[++i] ?? parsed.sttTimeoutSeconds);
    else if (arg === '--min-session-seconds') parsed.minSessionSeconds = Number(argv[++i] ?? parsed.minSessionSeconds);
    else if (arg === '--min-transcript-chars') parsed.minTranscriptChars = Number(argv[++i] ?? parsed.minTranscriptChars);
    else if (arg === '--inject') parsed.injectMode = argv[++i] ?? parsed.injectMode;
    else if (arg === '--injector') parsed.injector = argv[++i] ?? parsed.injector;
    else if (arg === '--inject-timeout-seconds') parsed.injectTimeoutSeconds = Number(argv[++i] ?? parsed.injectTimeoutSeconds);
    else if (arg === '--commands') parsed.commands = true;
    else if (arg === '--no-commands') parsed.commands = false;
    else if (arg === '--command-dispatcher') parsed.commandDispatcher = argv[++i] ?? parsed.commandDispatcher;
    else if (arg === '--command-timeout-seconds') parsed.commandTimeoutSeconds = Number(argv[++i] ?? parsed.commandTimeoutSeconds);
    else if (arg === '--help') usage();
    else throw new Error(`unknown arg: ${arg}`);
  }

  if (!Number.isInteger(parsed.port) || parsed.port < 1 || parsed.port > 65535) {
    throw new Error(`invalid port: ${parsed.port}`);
  }
  if (!['none', 'clipboard', 'paste', 'submit', 'tmux', 'tmux-submit'].includes(parsed.injectMode)) {
    throw new Error(`invalid inject mode: ${parsed.injectMode}`);
  }
  for (const [name, value] of [
    ['stt-timeout-seconds', parsed.sttTimeoutSeconds],
    ['min-session-seconds', parsed.minSessionSeconds],
    ['min-transcript-chars', parsed.minTranscriptChars],
    ['inject-timeout-seconds', parsed.injectTimeoutSeconds],
    ['command-timeout-seconds', parsed.commandTimeoutSeconds],
  ]) {
    if (!Number.isFinite(value) || value < 0) throw new Error(`invalid ${name}: ${value}`);
  }

  parsed.wav = expandHome(parsed.wav);
  parsed.sttCommand = resolveExecutable(expandHome(parsed.sttCommand));
  parsed.sessionDir = expandHome(parsed.sessionDir || path.join(DEFAULT_LOG_DIR, 'sessions'));
  parsed.transcriptDir = expandHome(parsed.transcriptDir || path.join(DEFAULT_LOG_DIR, 'transcripts'));
  parsed.transcriptLog = expandHome(parsed.transcriptLog || path.join(DEFAULT_LOG_DIR, 'transcripts.jsonl'));
  parsed.injector = expandHome(parsed.injector);
  parsed.commandDispatcher = expandHome(parsed.commandDispatcher);

  return parsed;
}

function usage() {
  console.log(
    'usage: node scripts/roam-relay-receiver.mjs [--host 0.0.0.0] [--port 8765] [--wav out.wav] ' +
    '[--transcribe] [--inject none|clipboard|paste|submit|tmux|tmux-submit] [--commands]',
  );
  process.exit(0);
}

function expandHome(value) {
  if (!value || !value.startsWith('~')) return value;
  if (value === '~') return os.homedir();
  if (value.startsWith('~/')) return path.join(os.homedir(), value.slice(2));
  return value;
}

function timestampForFile(date) {
  const pad = (n, width = 2) => String(n).padStart(width, '0');
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
    '-',
    pad(date.getMilliseconds(), 3),
  ].join('');
}

function resolveExecutable(command) {
  if (!command || command.includes('/')) return command;
  const searchDirs = [
    ...((process.env.PATH || '').split(':').filter(Boolean)),
    '/opt/homebrew/bin',
    '/usr/local/bin',
    '/usr/bin',
    '/bin',
  ];

  for (const dir of searchDirs) {
    const candidate = path.join(dir, command);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      // Keep looking.
    }
  }

  return command;
}

function runCommand(command, commandArgs, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, {
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const cap = (current, chunk) => (current + chunk.toString('utf8')).slice(-20000);
    const timer = options.timeoutMs > 0
      ? setTimeout(() => {
          child.kill('SIGTERM');
          reject(new Error(`${command} timed out after ${options.timeoutMs}ms`));
        }, options.timeoutMs)
      : null;

    child.stdout.on('data', (chunk) => { stdout = cap(stdout, chunk); });
    child.stderr.on('data', (chunk) => { stderr = cap(stderr, chunk); });
    child.on('error', (error) => {
      if (timer) clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code, signal) => {
      if (timer) clearTimeout(timer);
      if (code === 0) {
        resolve({ stdout, stderr });
      } else {
        const detail = stderr.trim() || stdout.trim() || `signal=${signal ?? 'none'}`;
        reject(new Error(`${command} exited ${code}: ${detail}`));
      }
    });

    if (options.input !== undefined) child.stdin.end(options.input);
    else child.stdin.end();
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function shutdown() {
  server.close(() => {
    if (wavSink) wavSink.close();
    process.exit(0);
  });
  setTimeout(() => {
    if (wavSink) wavSink.close();
    process.exit(0);
  }, 1000).unref();
}

class WavSink {
  constructor(path) {
    this.fd = fs.openSync(path, 'w+');
    this.bytes = 0;
    fs.writeSync(this.fd, wavHeader(0), 0, 44, 0);
  }

  write(buffer) {
    fs.writeSync(this.fd, buffer);
    this.bytes += buffer.length;
    fs.writeSync(this.fd, wavHeader(this.bytes), 0, 44, 0);
  }

  close() {
    if (this.fd === null) return;
    fs.writeSync(this.fd, wavHeader(this.bytes), 0, 44, 0);
    fs.closeSync(this.fd);
    this.fd = null;
  }
}

function wavHeader(dataBytes) {
  const header = Buffer.alloc(44);
  header.write('RIFF', 0);
  header.writeUInt32LE(36 + dataBytes, 4);
  header.write('WAVE', 8);
  header.write('fmt ', 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(16000, 24);
  header.writeUInt32LE(16000 * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write('data', 36);
  header.writeUInt32LE(dataBytes, 40);
  return header;
}

if (args.wav) fs.mkdirSync(path.dirname(args.wav), { recursive: true });
if (args.transcribe) {
  fs.mkdirSync(args.sessionDir, { recursive: true });
  fs.mkdirSync(args.transcriptDir, { recursive: true });
  fs.mkdirSync(path.dirname(args.transcriptLog), { recursive: true });
}

wavSink = args.wav ? new WavSink(args.wav) : null;

server.listen(args.port, args.host, () => {
  console.log(`roam relay receiver listening on ${args.host}:${args.port}`);
  if (wavSink) console.log(`writing decoded PCM to ${args.wav}`);
  if (args.transcribe) {
    console.log(
      `transcribing sessions with ${args.sttCommand} model=${args.sttModel} ` +
      `inject=${args.injectMode}`,
    );
  }
  if (args.commands) console.log(`dispatching action events with ${args.commandDispatcher}`);
});
