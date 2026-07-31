package io.roam.relay;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity {
    private static final String PREFS = "roam-relay";
    private static final String KEY_HOST = "host";
    private static final String KEY_PORT = "port";
    private static final String EXTRA_HOST_SHORT = "host";
    private static final String EXTRA_PORT_SHORT = "port";
    private static final String EXTRA_AUTO_START = "autoStart";

    private EditText hostInput;
    private EditText portInput;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestRuntimePermissions();

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(48, 64, 48, 48);
        root.setGravity(Gravity.CENTER_HORIZONTAL);

        TextView title = new TextView(this);
        title.setText("Roam Relay");
        title.setTextSize(26);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));

        hostInput = new EditText(this);
        hostInput.setHint("Mac IP address");
        hostInput.setSingleLine(true);
        hostInput.setText(prefs.getString(KEY_HOST, ""));
        root.addView(hostInput, new LinearLayout.LayoutParams(-1, -2));

        portInput = new EditText(this);
        portInput.setHint("Port");
        portInput.setSingleLine(true);
        portInput.setText(String.valueOf(prefs.getInt(KEY_PORT, 8765)));
        root.addView(portInput, new LinearLayout.LayoutParams(-1, -2));

        Button start = new Button(this);
        start.setText("Start Relay");
        start.setOnClickListener(v -> startRelay());
        root.addView(start, new LinearLayout.LayoutParams(-1, -2));

        Button stop = new Button(this);
        stop.setText("Stop Relay");
        stop.setOnClickListener(v -> stopService(new Intent(this, RoamRelayService.class)));
        root.addView(stop, new LinearLayout.LayoutParams(-1, -2));

        TextView note = new TextView(this);
        note.setText("Keep this app allowed for Bluetooth, notifications, and unrestricted battery use. The foreground notification is intentional.");
        note.setPadding(0, 32, 0, 0);
        root.addView(note, new LinearLayout.LayoutParams(-1, -2));

        setContentView(root);
        applyLaunchExtras(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyLaunchExtras(intent);
    }

    private void startRelay() {
        String host = hostInput.getText().toString().trim();
        int port = parsePort(portInput.getText().toString().trim());

        getSharedPreferences(PREFS, MODE_PRIVATE)
            .edit()
            .putString(KEY_HOST, host)
            .putInt(KEY_PORT, port)
            .apply();

        Intent intent = new Intent(this, RoamRelayService.class);
        intent.putExtra(RoamRelayService.EXTRA_HOST, host);
        intent.putExtra(RoamRelayService.EXTRA_PORT, port);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private int parsePort(String raw) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException ignored) {
            return 8765;
        }
    }

    private void requestRuntimePermissions() {
        List<String> permissions = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            addIfMissing(permissions, Manifest.permission.BLUETOOTH_SCAN);
            addIfMissing(permissions, Manifest.permission.BLUETOOTH_CONNECT);
        } else {
            addIfMissing(permissions, Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            addIfMissing(permissions, Manifest.permission.POST_NOTIFICATIONS);
        }
        if (!permissions.isEmpty()) {
            requestPermissions(permissions.toArray(new String[0]), 10);
        }
    }

    private void addIfMissing(List<String> permissions, String permission) {
        if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) {
            permissions.add(permission);
        }
    }

    private void applyLaunchExtras(Intent intent) {
        if (intent == null) return;

        String host = firstNonEmpty(
            intent.getStringExtra(RoamRelayService.EXTRA_HOST),
            intent.getStringExtra(EXTRA_HOST_SHORT)
        );
        if (host != null) {
            hostInput.setText(host);
        }

        if (intent.hasExtra(RoamRelayService.EXTRA_PORT)) {
            portInput.setText(String.valueOf(intent.getIntExtra(RoamRelayService.EXTRA_PORT, 8765)));
        } else if (intent.hasExtra(EXTRA_PORT_SHORT)) {
            portInput.setText(String.valueOf(intent.getIntExtra(EXTRA_PORT_SHORT, 8765)));
        }

        if (host != null || intent.getBooleanExtra(EXTRA_AUTO_START, false)) {
            new Handler(Looper.getMainLooper()).postDelayed(this::startRelay, 250);
        }
    }

    private String firstNonEmpty(String first, String second) {
        if (first != null && !first.trim().isEmpty()) return first.trim();
        if (second != null && !second.trim().isEmpty()) return second.trim();
        return null;
    }
}
