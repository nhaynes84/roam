package io.ironclan.roam.kiosk;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.Context;
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
 * <pre>adb shell am start -n io.ironclan.roam.kiosk/.MainActivity --ez clear_device_owner true</pre>
 *
 * <p>That calls {@link DevicePolicyManager#clearDeviceOwnerApp(String)}, which is the
 * only non-destructive way back. Keep it working.
 */
public class MainActivity extends Activity {

    /** Boolean intent extra; when true, the app gives up device-owner status. */
    public static final String EXTRA_CLEAR_DEVICE_OWNER = "clear_device_owner";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        DevicePolicyManager dpm =
                (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        String pkg = getPackageName();

        if (getIntent() != null
                && getIntent().getBooleanExtra(EXTRA_CLEAR_DEVICE_OWNER, false)) {
            clearDeviceOwner(dpm, pkg);
        }

        boolean owner = dpm != null && dpm.isDeviceOwnerApp(pkg);

        TextView tv = new TextView(this);
        tv.setText(owner ? "ROAM Kiosk\ndevice owner: YES" : "ROAM Kiosk\ndevice owner: no");
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
