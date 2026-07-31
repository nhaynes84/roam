package io.roam.relay;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

public class RelayControlReceiver extends BroadcastReceiver {
    public static final String ACTION_START = "io.roam.relay.START";
    public static final String ACTION_STOP = "io.roam.relay.STOP";

    private static final String EXTRA_HOST_SHORT = "host";
    private static final String EXTRA_PORT_SHORT = "port";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;

        String action = intent.getAction();
        if (ACTION_STOP.equals(action)) {
            context.stopService(new Intent(context, RoamRelayService.class));
            return;
        }

        if (!ACTION_START.equals(action)) return;

        String host = firstNonEmpty(
            intent.getStringExtra(RoamRelayService.EXTRA_HOST),
            intent.getStringExtra(EXTRA_HOST_SHORT)
        );
        int port = intent.hasExtra(RoamRelayService.EXTRA_PORT)
            ? intent.getIntExtra(RoamRelayService.EXTRA_PORT, 8765)
            : intent.getIntExtra(EXTRA_PORT_SHORT, 8765);

        Intent service = new Intent(context, RoamRelayService.class);
        service.putExtra(RoamRelayService.EXTRA_HOST, host);
        service.putExtra(RoamRelayService.EXTRA_PORT, port);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(service);
        } else {
            context.startService(service);
        }
    }

    private String firstNonEmpty(String first, String second) {
        if (first != null && !first.trim().isEmpty()) return first.trim();
        if (second != null && !second.trim().isEmpty()) return second.trim();
        return null;
    }
}
