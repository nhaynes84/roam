// Roam P2 — PDM mic audio streaming over BLE.
// Captures 16 kHz mono PCM and frames it as IMA ADPCM notifications.

#include "audio_stream.h"
#include <PDM.h>

static constexpr uint16_t PDM_RING_SAMPLES = 4096;
static constexpr uint16_t PDM_RING_MASK = PDM_RING_SAMPLES - 1;
static_assert((PDM_RING_SAMPLES & PDM_RING_MASK) == 0, "PDM ring must be power-of-two");

static int16_t _pdmRing[PDM_RING_SAMPLES];
static int16_t _pdmScratch[512];
static volatile uint16_t _pdmRead = 0;
static volatile uint16_t _pdmWrite = 0;
static volatile uint32_t _pdmOverflow = 0;

static const int16_t IMA_STEP_TABLE[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};

static const int8_t IMA_INDEX_TABLE[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
};

AudioStream audioStream;

static uint16_t nextPdmIndex(uint16_t index) {
    return (uint16_t)((index + 1) & PDM_RING_MASK);
}

static void resetPdmRing() {
    noInterrupts();
    _pdmRead = 0;
    _pdmWrite = 0;
    _pdmOverflow = 0;
    interrupts();
}

static bool popPdmSample(int16_t& sample) {
    noInterrupts();
    if (_pdmRead == _pdmWrite) {
        interrupts();
        return false;
    }

    sample = _pdmRing[_pdmRead];
    _pdmRead = nextPdmIndex(_pdmRead);
    interrupts();
    return true;
}

static void onPDMData() {
    int bytesAvailable = PDM.available();
    if (bytesAvailable <= 0) return;

    int toRead = bytesAvailable < (int)sizeof(_pdmScratch)
        ? bytesAvailable
        : (int)sizeof(_pdmScratch);
    toRead &= ~1;
    if (toRead <= 0) return;

    int bytesRead = PDM.read(_pdmScratch, toRead);
    int sampleCount = bytesRead / 2;

    for (int i = 0; i < sampleCount; i++) {
        uint16_t next = nextPdmIndex(_pdmWrite);
        if (next == _pdmRead) {
            _pdmOverflow += (uint32_t)(sampleCount - i);
            break;
        }

        _pdmRing[_pdmWrite] = _pdmScratch[i];
        _pdmWrite = next;
    }
}

bool AudioStream::begin() {
    PDM.setBufferSize(1024);
    PDM.onReceive(onPDMData);
    return true;
}

bool AudioStream::start() {
    if (_active) return true;

    resetPdmRing();
    resetEncoder();
    PDM.onReceive(onPDMData);
    PDM.setGain(30);
    if (!PDM.begin(1, 16000)) {
        Serial.println("audio_stream: failed to start PDM");
        return false;
    }

    _active = true;
    Serial.println("audio_stream: started 16k mono IMA ADPCM");
    return true;
}

void AudioStream::stop() {
    if (!_active) return;
    PDM.end();
    _active = false;
    Serial.println("audio_stream: stopped");
}

void AudioStream::poll(BLETextService& relay) {
    if (!_active) return;

    int16_t sample = 0;
    uint16_t processed = 0;
    while (processed < 1024 && popPdmSample(sample)) {
        appendSample(sample);
        flushFrame(relay, false);
        processed++;
    }
}

void AudioStream::resetEncoder() {
    _sequence = 0;
    _predictor = 0;
    _stepIndex = 0;
    _payloadLen = 0;
    _pendingNibble = 0;
    _hasPendingNibble = false;
    _frameStartMs = millis();
    _framePredictor = _predictor;
    _frameStepIndex = _stepIndex;
}

uint8_t AudioStream::encodeNibble(int16_t sample) {
    int step = IMA_STEP_TABLE[_stepIndex];
    int diff = sample - _predictor;
    uint8_t code = 0;

    if (diff < 0) {
        code = 8;
        diff = -diff;
    }

    int delta = step >> 3;
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

    int next = (code & 8) ? (_predictor - delta) : (_predictor + delta);
    if (next > 32767) next = 32767;
    if (next < -32768) next = -32768;
    _predictor = (int16_t)next;

    int nextIndex = (int)_stepIndex + IMA_INDEX_TABLE[code & 0x0f];
    if (nextIndex < 0) nextIndex = 0;
    if (nextIndex > 88) nextIndex = 88;
    _stepIndex = (uint8_t)nextIndex;

    return code & 0x0f;
}

void AudioStream::appendSample(int16_t sample) {
    beginFrameIfNeeded();
    uint8_t nibble = encodeNibble(sample);

    if (!_hasPendingNibble) {
        _pendingNibble = nibble;
        _hasPendingNibble = true;
        return;
    }

    if (_payloadLen < BLE_AUDIO_PAYLOAD_MAX_LEN) {
        _payload[_payloadLen++] = _pendingNibble | (nibble << 4);
    }
    _hasPendingNibble = false;
}

void AudioStream::beginFrameIfNeeded() {
    if (_payloadLen != 0 || _hasPendingNibble) return;
    _frameStartMs = millis();
    _framePredictor = _predictor;
    _frameStepIndex = _stepIndex;
}

void AudioStream::flushFrame(BLETextService& relay, bool force) {
    if (!force && _payloadLen < BLE_AUDIO_PAYLOAD_MAX_LEN) return;
    if (_payloadLen == 0) return;

    relay.notifyAudioFrame(RELAY_AUDIO_CODEC_IMA_ADPCM_16K, _sequence++, _frameStartMs,
                           _framePredictor, _frameStepIndex, _payload, _payloadLen);
    _payloadLen = 0;

    if (_hasPendingNibble) {
        _frameStartMs = millis();
        _framePredictor = _predictor;
        _frameStepIndex = _stepIndex;
        _payload[_payloadLen++] = _pendingNibble;
        _hasPendingNibble = false;
    }
}
