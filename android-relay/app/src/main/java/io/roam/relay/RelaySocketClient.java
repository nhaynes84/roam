package io.roam.relay;

import android.util.Log;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

final class RelaySocketClient {
    private static final String TAG = "RoamRelaySocket";
    private final Object lock = new Object();
    private final IncomingFrameListener listener;
    private Socket socket;
    private BufferedOutputStream out;
    private String host;
    private int port = 8765;
    private boolean enabled = false;
    private boolean connecting = false;
    private boolean reconnectQueued = false;

    interface IncomingFrameListener {
        void onTextFrame(String text);
    }

    RelaySocketClient(IncomingFrameListener listener) {
        this.listener = listener;
    }

    void connect(String host, int port) {
        if (host == null || host.isEmpty()) {
            close();
            Log.w(TAG, "No Mac host configured");
            return;
        }
        synchronized (lock) {
            closeLocked();
            this.host = host;
            this.port = port;
            enabled = true;
        }
        requestConnect(0);
    }

    void sendEvent(String json) {
        sendFrame(RelayProtocol.FRAME_EVENT, json.getBytes(StandardCharsets.UTF_8));
    }

    void sendAudio(byte[] packet) {
        sendFrame(RelayProtocol.FRAME_AUDIO, packet);
    }

    private void sendFrame(int type, byte[] payload) {
        if (payload == null || payload.length > 0xffff) return;
        synchronized (lock) {
            if (out == null) {
                requestConnect(0);
                return;
            }
            try {
                out.write(type & 0xff);
                out.write((payload.length >> 8) & 0xff);
                out.write(payload.length & 0xff);
                out.write(payload);
                out.flush();
            } catch (IOException e) {
                Log.e(TAG, "Mac socket write failed", e);
                closeLocked();
                requestConnect(1000);
            }
        }
    }

    void close() {
        synchronized (lock) {
            enabled = false;
            reconnectQueued = false;
            connecting = false;
            closeLocked();
        }
    }

    private void requestConnect(long delayMs) {
        synchronized (lock) {
            if (!enabled || connecting || reconnectQueued || out != null) return;
            reconnectQueued = true;
        }

        new Thread(() -> {
            if (delayMs > 0) {
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
            }

            String targetHost;
            int targetPort;
            synchronized (lock) {
                reconnectQueued = false;
                if (!enabled || connecting || out != null || host == null || host.isEmpty()) return;
                connecting = true;
                targetHost = host;
                targetPort = port;
            }

            try {
                Socket s = new Socket();
                s.connect(new InetSocketAddress(targetHost, targetPort), 4000);
                BufferedOutputStream stream = new BufferedOutputStream(s.getOutputStream());
                synchronized (lock) {
                    socket = s;
                    out = stream;
                    connecting = false;
                }
                Log.i(TAG, "Connected to " + targetHost + ":" + targetPort);
                startReadLoop(s);
            } catch (IOException e) {
                Log.e(TAG, "Mac socket connect failed", e);
                synchronized (lock) {
                    connecting = false;
                    closeLocked();
                }
                requestConnect(3000);
            }
        }, "roam-mac-connect").start();
    }

    private void closeLocked() {
        try {
            if (socket != null) socket.close();
        } catch (IOException ignored) {
        }
        socket = null;
        out = null;
    }

    private void startReadLoop(Socket activeSocket) {
        new Thread(() -> readLoop(activeSocket), "roam-mac-read").start();
    }

    private void readLoop(Socket activeSocket) {
        try {
            BufferedInputStream in = new BufferedInputStream(activeSocket.getInputStream());
            byte[] header = new byte[3];
            while (true) {
                synchronized (lock) {
                    if (!enabled || socket != activeSocket) return;
                }

                if (!readFully(in, header)) break;
                int type = header[0] & 0xff;
                int length = ((header[1] & 0xff) << 8) | (header[2] & 0xff);
                byte[] payload = new byte[length];
                if (!readFully(in, payload)) break;

                if (type == RelayProtocol.FRAME_TEXT) {
                    try {
                        listener.onTextFrame(new String(payload, StandardCharsets.UTF_8));
                    } catch (RuntimeException e) {
                        Log.e(TAG, "Mac text frame handler failed", e);
                    }
                } else {
                    Log.w(TAG, "Ignoring Mac frame type=" + type + " length=" + length);
                }
            }
        } catch (IOException e) {
            synchronized (lock) {
                if (enabled && socket == activeSocket) {
                    Log.e(TAG, "Mac socket read failed", e);
                }
            }
        }

        boolean shouldReconnect = false;
        synchronized (lock) {
            if (socket == activeSocket) {
                closeLocked();
                shouldReconnect = enabled;
            }
        }
        if (shouldReconnect) requestConnect(1000);
    }

    private boolean readFully(BufferedInputStream in, byte[] buffer) throws IOException {
        int offset = 0;
        while (offset < buffer.length) {
            int read = in.read(buffer, offset, buffer.length - offset);
            if (read < 0) return false;
            offset += read;
        }
        return true;
    }
}
