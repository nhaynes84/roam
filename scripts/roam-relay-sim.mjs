#!/usr/bin/env node

import net from 'node:net';

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

const AUDIO_PAYLOAD_BYTES = 232;
const AUDIO_SAMPLES_PER_FRAME = AUDIO_PAYLOAD_BYTES * 2;

const args = parseArgs(process.argv.slice(2));
const socket = net.createConnection({ host: args.host, port: args.port }, () => {
  for (let session = 0; session < args.sessions; session += 1) {
    sendSession(session);
  }

  socket.end();
});

socket.on('error', (error) => {
  console.error(error.message);
  process.exitCode = 1;
});

function sendFrame(type, payload) {
  const header = Buffer.alloc(3);
  header[0] = type;
  header.writeUInt16BE(payload.length, 1);
  socket.write(Buffer.concat([header, payload]));
}

function sendSession(session) {
  const baseMillis = 100 + session * (args.frames * 30 + 1000);
  sendFrame(1, Buffer.from(JSON.stringify({
    version: 1,
    eventType: 1,
    actionId: 2,
    profileId: 1,
    roamMillis: baseMillis,
  })));
  sendFrame(1, Buffer.from(JSON.stringify({
    version: 1,
    eventType: 2,
    actionId: 0,
    profileId: 1,
    roamMillis: baseMillis + 1,
  })));

  const encoder = new ImaEncoder();
  for (let seq = 0; seq < args.frames; seq += 1) {
    const payload = Buffer.alloc(AUDIO_PAYLOAD_BYTES);
    const predictor = encoder.predictor;
    const stepIndex = encoder.stepIndex;
    for (let i = 0; i < payload.length; i += 1) {
      const sampleA = toneSample(seq * AUDIO_SAMPLES_PER_FRAME + i * 2);
      const sampleB = toneSample(seq * AUDIO_SAMPLES_PER_FRAME + i * 2 + 1);
      payload[i] = encoder.encode(sampleA) | (encoder.encode(sampleB) << 4);
    }

    const packet = Buffer.alloc(12 + payload.length);
    packet[0] = 1;
    packet[1] = 2;
    packet.writeUInt16LE(seq, 2);
    packet.writeUInt32LE(baseMillis + 1 + seq * 29, 4);
    packet.writeInt16LE(predictor, 8);
    packet[10] = stepIndex;
    packet[11] = 0;
    payload.copy(packet, 12);
    sendFrame(2, packet);
  }

  sendFrame(1, Buffer.from(JSON.stringify({
    version: 1,
    eventType: 3,
    actionId: 0,
    profileId: 1,
    roamMillis: baseMillis + 1 + args.frames * 29,
  })));
}

function toneSample(index) {
  return Math.round(Math.sin((index / 16000) * Math.PI * 2 * 440) * 9000);
}

class ImaEncoder {
  constructor() {
    this.predictor = 0;
    this.stepIndex = 0;
  }

  encode(sample) {
    const step = IMA_STEP_TABLE[this.stepIndex];
    let diff = sample - this.predictor;
    let code = 0;

    if (diff < 0) {
      code = 8;
      diff = -diff;
    }

    let delta = step >> 3;
    if (diff >= step) {
      code |= 4;
      diff -= step;
      delta += step;
    }
    if (diff >= (step >> 1)) {
      code |= 2;
      diff -= step >> 1;
      delta += step >> 1;
    }
    if (diff >= (step >> 2)) {
      code |= 1;
      delta += step >> 2;
    }

    this.predictor = code & 8 ? this.predictor - delta : this.predictor + delta;
    this.predictor = Math.max(-32768, Math.min(32767, this.predictor));

    this.stepIndex += IMA_INDEX_TABLE[code & 0x0f];
    this.stepIndex = Math.max(0, Math.min(88, this.stepIndex));

    return code & 0x0f;
  }
}

function parseArgs(argv) {
  const parsed = {
    host: '127.0.0.1',
    port: 8765,
    frames: 50,
    sessions: 1,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--host') parsed.host = argv[++i] ?? parsed.host;
    else if (arg === '--port') parsed.port = Number(argv[++i] ?? parsed.port);
    else if (arg === '--frames') parsed.frames = Number(argv[++i] ?? parsed.frames);
    else if (arg === '--sessions') parsed.sessions = Number(argv[++i] ?? parsed.sessions);
    else if (arg === '--help') usage();
  }

  if (!Number.isInteger(parsed.port) || parsed.port < 1 || parsed.port > 65535) {
    throw new Error(`invalid port: ${parsed.port}`);
  }
  if (!Number.isInteger(parsed.frames) || parsed.frames < 1) {
    throw new Error(`invalid frame count: ${parsed.frames}`);
  }
  if (!Number.isInteger(parsed.sessions) || parsed.sessions < 1) {
    throw new Error(`invalid session count: ${parsed.sessions}`);
  }

  return parsed;
}

function usage() {
  console.log('usage: node scripts/roam-relay-sim.mjs [--host 127.0.0.1] [--port 8765] [--frames 50] [--sessions 1]');
  process.exit(0);
}
