package io.ironclan.roam.kiosk;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * The component named to {@code dpm set-device-owner}.
 *
 * <p>It intentionally does nothing but log. Its only job right now is to exist so the
 * package can hold device-owner status; lock-task and managed-configuration policy get
 * hung off it later, once there is a tested way back out of kiosk mode.
 */
public class KioskDeviceAdminReceiver extends DeviceAdminReceiver {

    static final String TAG = "RoamKioskAdmin";

    @Override
    public void onEnabled(Context context, Intent intent) {
        Log.i(TAG, "device admin enabled");
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        Log.i(TAG, "device admin disabled");
    }

    @Override
    public void onProfileProvisioningComplete(Context context, Intent intent) {
        Log.i(TAG, "provisioning complete");
    }

    @Override
    public CharSequence onDisableRequested(Context context, Intent intent) {
        return "ROAM Touch will lose device-owner policy control.";
    }
}
