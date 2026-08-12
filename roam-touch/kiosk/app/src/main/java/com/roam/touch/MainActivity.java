package com.roam.touch;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.TextView;

/**
 * Status screen. No kiosk UI yet — this only reports whether the package holds
 * device-owner status, and carries the escape hatch.
 *
 * <p><b>Escape hatch.</b> Device owner cannot normally be undone without a factory
 * reset, so the app can relinquish it on demand:
 *
 * <pre>adb shell am start -n com.roam.touch/.MainActivity --ez clear_device_owner true</pre>
 *
 * <p>That calls {@link DevicePolicyManager#clearDeviceOwnerApp(String)}, which is the
 * only non-destructive way back. Keep it working.
 *
 * <p>⚠️ <b>Why this activity is {@code singleTop} and overrides {@code onNewIntent}.</b>
 * Verified on sailfish 2026-08-11: a device-owner package is <i>immune to
 * {@code am force-stop}</i> — the pid survives, so this activity stays resident
 * indefinitely. {@code am start} carries {@code FLAG_ACTIVITY_NEW_TASK}, which merely
 * brings the existing task forward; with the default {@code standard} launch mode and
 * no {@code onNewIntent}, the extra was silently dropped and the hatch did nothing.
 * Handling the intent in both entry points is what makes the command above work.
 * Do not "simplify" either of them away.
 */
public class MainActivity extends Activity {

    /** Boolean intent extra; when true, the app gives up device-owner status. */
    public static final String EXTRA_CLEAR_DEVICE_OWNER = "clear_device_owner";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    private void handleIntent(Intent intent) {
        DevicePolicyManager dpm =
                (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        String pkg = getPackageName();

        if (intent != null && intent.getBooleanExtra(EXTRA_CLEAR_DEVICE_OWNER, false)) {
            clearDeviceOwner(dpm, pkg);
        }

        boolean owner = dpm != null && dpm.isDeviceOwnerApp(pkg);

        TextView tv = new TextView(this);
        tv.setText(owner ? "ROAM Touch\ndevice owner: YES" : "ROAM Touch\ndevice owner: no");
        tv.setGravity(Gravity.CENTER);
        tv.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        tv.setTextColor(Color.WHITE);
        tv.setBackgroundColor(Color.BLACK);
        setContentView(tv);

        Log.i(KioskDeviceAdminReceiver.TAG, "device owner = " + owner);
    }

    private void clearDeviceOwner(DevicePolicyManager dpm, String pkg) {
        if (dpm == null || !dpm.isDeviceOwnerApp(pkg)) {
            Log.w(KioskDeviceAdminReceiver.TAG, "clear requested but not device owner");
            return;
        }
        try {
            dpm.clearDeviceOwnerApp(pkg);
            Log.i(KioskDeviceAdminReceiver.TAG, "device owner cleared");
        } catch (Exception e) {
            Log.e(KioskDeviceAdminReceiver.TAG, "clearDeviceOwnerApp failed", e);
        }
    }
}
