package io.roam.relay;

import java.util.UUID;

final class RelayProtocol {
    static final UUID SERVICE_UUID = uuid16(0xff00);
    static final UUID TEXT_UUID = uuid16(0xff01);
    static final UUID EVENT_UUID = uuid16(0xff02);
    static final UUID AUDIO_UUID = uuid16(0xff03);
    static final UUID CONTROL_UUID = uuid16(0xff04);
    static final UUID CCCD_UUID = uuid16(0x2902);

    static final int FRAME_EVENT = 1;
    static final int FRAME_AUDIO = 2;
    static final int FRAME_TEXT = 3;

    static final int EVENT_ACTION = 1;
    static final int ACTION_DICTATION_ANDROID = 2;
    static final int CONTROL_START_AUDIO = 1;
    static final int CONTROL_STOP_AUDIO = 2;
    static final int CONTROL_STATUS_REQUEST = 3;

    static final int BLE_TEXT_CHUNK_BYTES = 120;

    private RelayProtocol() {}

    static UUID uuid16(int value) {
        return UUID.fromString(String.format("0000%04x-0000-1000-8000-00805f9b34fb", value & 0xffff));
    }
}
