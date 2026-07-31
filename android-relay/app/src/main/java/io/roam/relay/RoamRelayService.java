package io.roam.relay;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelUuid;
import android.util.Log;

import java.lang.reflect.Method;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.nio.charset.StandardCharsets;

public class RoamRelayService extends Service {
    public static final String EXTRA_HOST = "io.roam.relay.HOST";
    public static final String EXTRA_PORT = "io.roam.relay.PORT";

    private static final String TAG = "RoamRelayService";
    private static final String CHANNEL_ID = "roam-relay";
    private static final int NOTIFICATION_ID = 42;
    private static final int MAX_PENDING_TEXTS = 8;
    private static final long GATT_TEXT_SETTLE_MS = 300;
    private static final long ROAM_STATUS_POLL_MS = 15000;
    private static final long ROAM_STALE_MS = 45000;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final RelaySocketClient socketClient = new RelaySocketClient(this::handleMacText);

    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic textChar;
    private BluetoothGattCharacteristic eventChar;
    private BluetoothGattCharacteristic audioChar;
    private BluetoothGattCharacteristic controlChar;
    private boolean audioStreaming = false;
    private boolean gattBusy = false;
    private boolean scanning = false;
    private boolean bleConnecting = false;
    private long gattOperationId = 0;
    private long activeGattSettleMs = 0;
    private final ArrayDeque<QueuedGattOperation> gattQueue = new ArrayDeque<>();
    private final ArrayDeque<String> pendingTexts = new ArrayDeque<>();
    private final Set<String> loggedScanDevices = new HashSet<>();
    private final Set<String> bondedRoamAddresses = new HashSet<>();
    private long lastRoamActivityMs = 0;
    private long lastScanHeartbeatMs = 0;
    private final Runnable scanRunnable = this::startScan;
    private final Runnable bondedFallbackRunnable = this::connectBondedRoam;
    private final Runnable roamWatchdogRunnable = this::watchRoamConnection;

    private interface GattOperation {
        boolean start();
    }

    private static final class QueuedGattOperation {
        final GattOperation operation;
        final long settleMs;

        QueuedGattOperation(GattOperation operation, long settleMs) {
            this.operation = operation;
            this.settleMs = settleMs;
        }
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            if (gatt != null || bleConnecting) return;

            BluetoothDevice device = result.getDevice();
            String name = hasBluetoothConnectPermission() ? device.getName() : null;
            if (name == null && result.getScanRecord() != null) {
                name = result.getScanRecord().getDeviceName();
            }

            boolean serviceMatch = result.getScanRecord() != null
                && result.getScanRecord().getServiceUuids() != null
                && result.getScanRecord().getServiceUuids().contains(new ParcelUuid(RelayProtocol.SERVICE_UUID));
            boolean bondedMatch = bondedRoamAddresses.contains(device.getAddress());

            if (serviceMatch || isRoamName(name) || bondedMatch) {
                Log.i(TAG, "Found Roam candidate: " + name + " " + device.getAddress());
                stopScan();
                connect(device);
            } else {
                logScanResult(result, name);
            }
        }

        @Override
        public void onScanFailed(int errorCode) {
            scanning = false;
            Log.e(TAG, "BLE scan failed: " + errorCode);
            scheduleScan(errorCode == 6 ? 10000 : 3000);
        }
    };

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            if (RoamRelayService.this.gatt != null && RoamRelayService.this.gatt != gatt) {
                Log.w(TAG, "Ignoring callback from stale GATT instance");
                if (hasBluetoothConnectPermission()) {
                    gatt.close();
                }
                return;
            }

            if (newState == BluetoothProfile.STATE_CONNECTED) {
                Log.i(TAG, "BLE connected");
                bleConnecting = false;
                markRoamActivity();
                if (hasBluetoothConnectPermission()) {
                    if (!gatt.requestMtu(247)) {
                        gatt.discoverServices();
                    }
                }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                Log.w(TAG, "BLE disconnected, status=" + status);
                bleConnecting = false;
                audioStreaming = false;
                closeGatt(status != BluetoothGatt.GATT_SUCCESS);
                scheduleScan();
            }
        }

        @Override
        public void onMtuChanged(BluetoothGatt gatt, int mtu, int status) {
            Log.i(TAG, "BLE MTU=" + mtu + " status=" + status);
            if (status == BluetoothGatt.GATT_SUCCESS) {
                markRoamActivity();
            }
            if (hasBluetoothConnectPermission()) {
                gatt.discoverServices();
            }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Service discovery failed: " + status);
                closeGatt();
                scheduleScan();
                return;
            }

            BluetoothGattService service = gatt.getService(RelayProtocol.SERVICE_UUID);
            if (service == null) {
                Log.e(TAG, "Roam FF00 service missing");
                logGattServices(gatt);
                closeGatt(true);
                scheduleScan(8000);
                return;
            }
            markRoamActivity();

            textChar = service.getCharacteristic(RelayProtocol.TEXT_UUID);
            eventChar = service.getCharacteristic(RelayProtocol.EVENT_UUID);
            audioChar = service.getCharacteristic(RelayProtocol.AUDIO_UUID);
            controlChar = service.getCharacteristic(RelayProtocol.CONTROL_UUID);
            if (eventChar == null || controlChar == null) {
                Log.e(TAG, "Roam relay characteristics missing");
                logGattServices(gatt);
                closeGatt(true);
                scheduleScan(8000);
                return;
            }
            if (audioChar == null) {
                Log.w(TAG, "Roam audio characteristic FF03 missing; continuing with event/control relay only");
            }
            if (textChar == null) {
                Log.w(TAG, "Roam text characteristic FF01 missing; Mac feedback display unavailable");
            }

            subscribe(eventChar);
            if (audioChar != null) {
                subscribe(audioChar);
            }
            writeControl(RelayProtocol.CONTROL_STATUS_REQUEST);
            flushPendingTexts();
            Log.i(TAG, "Roam relay service ready");
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            handleCharacteristic(characteristic.getUuid(), characteristic.getValue());
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, byte[] value) {
            handleCharacteristic(characteristic.getUuid(), value);
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt gatt, BluetoothGattDescriptor descriptor, int status) {
            Log.d(TAG, "Descriptor write status=" + status);
            if (status == BluetoothGatt.GATT_SUCCESS) {
                markRoamActivity();
            }
            completeGattOperation();
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            Log.d(TAG, "Characteristic write status=" + status);
            if (status == BluetoothGatt.GATT_SUCCESS) {
                markRoamActivity();
            }
            completeGattOperation();
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String host = intent != null ? intent.getStringExtra(EXTRA_HOST) : "";
        int port = intent != null ? intent.getIntExtra(EXTRA_PORT, 8765) : 8765;

        startForeground(NOTIFICATION_ID, buildNotification("Relaying Roam"));
        socketClient.connect(host, port);
        startScan();
        startRoamWatchdog();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(roamWatchdogRunnable);
        stopScan();
        closeGatt();
        socketClient.close();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void startScan() {
        handler.removeCallbacks(scanRunnable);
        if (scanning || gatt != null || bleConnecting) return;

        if (!hasBluetoothScanPermission()) {
            Log.e(TAG, "Missing Bluetooth scan permission");
            return;
        }

        BluetoothManager manager = getSystemService(BluetoothManager.class);
        BluetoothAdapter adapter = manager != null ? manager.getAdapter() : null;
        scanner = adapter != null ? adapter.getBluetoothLeScanner() : null;
        if (scanner == null) {
            Log.e(TAG, "BLE scanner unavailable");
            return;
        }
        refreshBondedRoams(adapter);

        ScanSettings settings = new ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build();
        loggedScanDevices.clear();
        lastScanHeartbeatMs = 0;
        scanner.startScan(null, settings, scanCallback);
        scanning = true;
        Log.i(TAG, "Scanning for Roam");
        handler.postDelayed(bondedFallbackRunnable, 6000);
    }

    private void scheduleScan() {
        scheduleScan(3000);
    }

    private void scheduleScan(long delayMs) {
        handler.removeCallbacks(scanRunnable);
        handler.postDelayed(scanRunnable, delayMs);
    }

    private void stopScan() {
        handler.removeCallbacks(bondedFallbackRunnable);
        if (scanner != null && scanning && hasBluetoothScanPermission()) {
            try {
                scanner.stopScan(scanCallback);
            } catch (IllegalStateException e) {
                Log.w(TAG, "BLE scan stop failed", e);
            }
        }
        scanning = false;
    }

    private void refreshBondedRoams(BluetoothAdapter adapter) {
        bondedRoamAddresses.clear();
        if (adapter == null || !hasBluetoothConnectPermission()) return;
        for (BluetoothDevice device : adapter.getBondedDevices()) {
            String name = device.getName();
            if (isRoamName(name)) {
                bondedRoamAddresses.add(device.getAddress());
                Log.i(TAG, "Bonded Roam available: " + name + " " + device.getAddress());
            }
        }
    }

    private void connectBondedRoam() {
        if (!scanning || gatt != null || bleConnecting || bondedRoamAddresses.isEmpty() || !hasBluetoothConnectPermission()) return;
        BluetoothManager manager = getSystemService(BluetoothManager.class);
        BluetoothAdapter adapter = manager != null ? manager.getAdapter() : null;
        if (adapter == null) return;
        String address = bondedRoamAddresses.iterator().next();
        BluetoothDevice device = adapter.getRemoteDevice(address);
        Log.i(TAG, "Trying bonded Roam fallback: " + address);
        stopScan();
        connect(device, true);
    }

    private void connect(BluetoothDevice device) {
        connect(device, false);
    }

    private void connect(BluetoothDevice device, boolean autoConnect) {
        if (!hasBluetoothConnectPermission()) {
            Log.e(TAG, "Missing Bluetooth connect permission");
            return;
        }
        if (gatt != null || bleConnecting) return;

        bleConnecting = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            gatt = device.connectGatt(this, autoConnect, gattCallback, BluetoothDevice.TRANSPORT_LE);
        } else {
            gatt = device.connectGatt(this, autoConnect, gattCallback);
        }
        if (gatt == null) {
            bleConnecting = false;
            Log.e(TAG, "BLE connectGatt returned null");
            scheduleScan();
            return;
        }
        markRoamActivity();
    }

    private void closeGatt() {
        closeGatt(false);
    }

    private void closeGatt(boolean refreshCache) {
        if (gatt != null && hasBluetoothConnectPermission()) {
            if (refreshCache) {
                refreshGattCache(gatt);
            }
            gatt.close();
        }
        gatt = null;
        textChar = null;
        eventChar = null;
        audioChar = null;
        controlChar = null;
        bleConnecting = false;
        lastRoamActivityMs = 0;
        clearGattQueue();
    }

    private void subscribe(BluetoothGattCharacteristic characteristic) {
        enqueueGattOperation(() -> {
            if (gatt == null || characteristic == null || !hasBluetoothConnectPermission()) return false;
            if (!gatt.setCharacteristicNotification(characteristic, true)) return false;
            BluetoothGattDescriptor descriptor = characteristic.getDescriptor(RelayProtocol.CCCD_UUID);
            if (descriptor == null) return false;
            if (Build.VERSION.SDK_INT >= 33) {
                return gatt.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE) == 0;
            }
            descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            return gatt.writeDescriptor(descriptor);
        });
    }

    private void handleCharacteristic(java.util.UUID uuid, byte[] value) {
        if (value == null) return;
        markRoamActivity();
        if (RelayProtocol.EVENT_UUID.equals(uuid)) {
            handleEvent(value);
        } else if (RelayProtocol.AUDIO_UUID.equals(uuid)) {
            socketClient.sendAudio(value);
        }
    }

    private void handleEvent(byte[] packet) {
        if (packet.length < 8) return;
        int version = packet[0] & 0xff;
        int eventType = packet[1] & 0xff;
        int actionId = packet[2] & 0xff;
        int profileId = packet[3] & 0xff;
        long timestamp = uint32le(packet, 4);

        String json = String.format(Locale.US,
            "{\"version\":%d,\"eventType\":%d,\"actionId\":%d,\"profileId\":%d,\"roamMillis\":%d}",
            version, eventType, actionId, profileId, timestamp);
        socketClient.sendEvent(json);

        if (eventType == RelayProtocol.EVENT_ACTION && actionId == RelayProtocol.ACTION_DICTATION_ANDROID) {
            audioStreaming = !audioStreaming;
            writeControl(audioStreaming ? RelayProtocol.CONTROL_START_AUDIO : RelayProtocol.CONTROL_STOP_AUDIO);
        }
    }

    private void startRoamWatchdog() {
        handler.removeCallbacks(roamWatchdogRunnable);
        handler.postDelayed(roamWatchdogRunnable, ROAM_STATUS_POLL_MS);
    }

    private void watchRoamConnection() {
        long now = System.currentTimeMillis();
        if (gatt != null) {
            long idleMs = lastRoamActivityMs == 0 ? 0 : now - lastRoamActivityMs;
            if (lastRoamActivityMs != 0 && idleMs >= ROAM_STALE_MS) {
                Log.w(TAG, "Roam BLE connection stale for " + idleMs + "ms; resetting GATT and scanning");
                audioStreaming = false;
                closeGatt(true);
                scheduleScan(500);
            } else if (controlChar != null
                    && lastRoamActivityMs != 0
                    && idleMs >= ROAM_STATUS_POLL_MS
                    && !gattBusy
                    && gattQueue.isEmpty()) {
                writeControl(RelayProtocol.CONTROL_STATUS_REQUEST);
            }
        } else if (!scanning) {
            scheduleScan(500);
        }
        handler.postDelayed(roamWatchdogRunnable, ROAM_STATUS_POLL_MS);
    }

    private void markRoamActivity() {
        lastRoamActivityMs = System.currentTimeMillis();
    }

    private void writeControl(int command) {
        byte[] packet = new byte[] { 1, (byte) command };
        enqueueGattOperation(() -> {
            if (gatt == null || controlChar == null || !hasBluetoothConnectPermission()) return false;
            controlChar.setValue(packet);
            if (Build.VERSION.SDK_INT >= 33) {
                return gatt.writeCharacteristic(controlChar, packet, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == 0;
            }
            controlChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
            return gatt.writeCharacteristic(controlChar);
        });
    }

    private void handleMacText(String text) {
        handler.post(() -> writeText(text));
    }

    private void writeText(String text) {
        if (text == null) return;
        String trimmed = text.trim();
        if (trimmed.isEmpty()) return;

        if (gatt == null || textChar == null || !hasBluetoothConnectPermission()) {
            queueText(trimmed);
            Log.w(TAG, "Queued Mac text until Roam text characteristic is ready: " + trimmed);
            return;
        }

        for (byte[] chunk : splitUtf8(trimmed, RelayProtocol.BLE_TEXT_CHUNK_BYTES)) {
            writeTextChunk(chunk);
        }
    }

    private void writeTextChunk(byte[] chunk) {
        enqueueGattOperation(() -> {
            if (gatt == null || textChar == null || !hasBluetoothConnectPermission()) return false;
            textChar.setValue(chunk);
            if (Build.VERSION.SDK_INT >= 33) {
                return gatt.writeCharacteristic(textChar, chunk, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == 0;
            }
            textChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
            return gatt.writeCharacteristic(textChar);
        }, GATT_TEXT_SETTLE_MS);
    }

    private void queueText(String text) {
        while (pendingTexts.size() >= MAX_PENDING_TEXTS) {
            pendingTexts.poll();
        }
        pendingTexts.add(text);
    }

    private void flushPendingTexts() {
        while (!pendingTexts.isEmpty()) {
            writeText(pendingTexts.poll());
        }
    }

    private List<byte[]> splitUtf8(String text, int maxBytes) {
        ArrayList<byte[]> chunks = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        int currentBytes = 0;

        for (int offset = 0; offset < text.length(); ) {
            int codePoint = text.codePointAt(offset);
            String piece = new String(Character.toChars(codePoint));
            int pieceBytes = piece.getBytes(StandardCharsets.UTF_8).length;

            if (currentBytes > 0 && currentBytes + pieceBytes > maxBytes) {
                chunks.add(current.toString().getBytes(StandardCharsets.UTF_8));
                current.setLength(0);
                currentBytes = 0;
            }

            current.append(piece);
            currentBytes += pieceBytes;
            offset += Character.charCount(codePoint);
        }

        if (currentBytes > 0) {
            chunks.add(current.toString().getBytes(StandardCharsets.UTF_8));
        }
        return chunks;
    }

    private void enqueueGattOperation(GattOperation operation) {
        enqueueGattOperation(operation, 0);
    }

    private void enqueueGattOperation(GattOperation operation, long settleMs) {
        handler.post(() -> {
            gattQueue.add(new QueuedGattOperation(operation, settleMs));
            drainGattQueue();
        });
    }

    private void drainGattQueue() {
        if (gattBusy) return;
        QueuedGattOperation queued = gattQueue.poll();
        if (queued == null) return;

        gattBusy = true;
        activeGattSettleMs = queued.settleMs;
        long operationId = ++gattOperationId;
        boolean started;
        try {
            started = queued.operation.start();
        } catch (RuntimeException e) {
            Log.e(TAG, "GATT operation failed before callback", e);
            started = false;
        }
        if (!started) {
            gattBusy = false;
            activeGattSettleMs = 0;
            drainGattQueue();
            return;
        }
        handler.postDelayed(() -> timeoutGattOperation(operationId), 5000);
    }

    private void completeGattOperation() {
        handler.post(() -> {
            long settleMs = activeGattSettleMs;
            activeGattSettleMs = 0;
            if (settleMs > 0) {
                handler.postDelayed(() -> {
                    gattBusy = false;
                    drainGattQueue();
                }, settleMs);
            } else {
                gattBusy = false;
                drainGattQueue();
            }
        });
    }

    private void timeoutGattOperation(long operationId) {
        if (!gattBusy || operationId != gattOperationId) return;
        Log.w(TAG, "GATT operation timed out");
        gattBusy = false;
        activeGattSettleMs = 0;
        drainGattQueue();
    }

    private void clearGattQueue() {
        gattQueue.clear();
        gattBusy = false;
        activeGattSettleMs = 0;
        gattOperationId += 1;
    }

    private long uint32le(byte[] data, int offset) {
        return ((long)data[offset] & 0xff)
            | (((long)data[offset + 1] & 0xff) << 8)
            | (((long)data[offset + 2] & 0xff) << 16)
            | (((long)data[offset + 3] & 0xff) << 24);
    }

    private boolean isRoamName(String name) {
        return name != null && name.toLowerCase(Locale.US).contains("roam");
    }

    private void logScanResult(ScanResult result, String name) {
        List<ParcelUuid> serviceUuids = result.getScanRecord() != null
            ? result.getScanRecord().getServiceUuids()
            : null;
        boolean hasName = name != null && !name.trim().isEmpty();
        boolean hasServices = serviceUuids != null && !serviceUuids.isEmpty();
        long now = System.currentTimeMillis();

        if (!hasName && !hasServices) {
            if (now - lastScanHeartbeatMs > 15000) {
                lastScanHeartbeatMs = now;
                Log.d(TAG, "BLE scan active; ignoring unnamed advertisements");
            }
            return;
        }

        String key = result.getDevice().getAddress() + "|" + name + "|" + serviceUuids;
        if (loggedScanDevices.add(key)) {
            Log.i(TAG, "BLE seen name=" + name
                + " address=" + result.getDevice().getAddress()
                + " rssi=" + result.getRssi()
                + " services=" + serviceUuids);
        }
    }

    private void logGattServices(BluetoothGatt targetGatt) {
        if (targetGatt == null) return;

        for (BluetoothGattService service : targetGatt.getServices()) {
            StringBuilder chars = new StringBuilder();
            for (BluetoothGattCharacteristic characteristic : service.getCharacteristics()) {
                if (chars.length() > 0) chars.append(",");
                chars.append(characteristic.getUuid());
            }
            Log.i(TAG, "GATT service " + service.getUuid() + " chars=[" + chars + "]");
        }
    }

    private void refreshGattCache(BluetoothGatt targetGatt) {
        try {
            Method refresh = targetGatt.getClass().getMethod("refresh");
            Object result = refresh.invoke(targetGatt);
            Log.i(TAG, "GATT cache refresh requested: " + result);
        } catch (ReflectiveOperationException | RuntimeException e) {
            Log.w(TAG, "GATT cache refresh unavailable", e);
        }
    }

    private boolean hasBluetoothScanPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasBluetoothConnectPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Roam Relay",
            NotificationManager.IMPORTANCE_LOW
        );
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text) {
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        return builder
            .setContentTitle("Roam Relay")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setOngoing(true)
            .build();
    }
}
