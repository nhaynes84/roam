package com.roam.touch;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/**
 * The component named to {@code dpm set-device-owner}.
 *
 * <p>It intentionally does nothing but log. Its only job is to exist so the package can
 * hold device-owner status, which buys managed configuration, policy and silent installs.
 *
 * <p>⚠️ Renaming this class re-provisions the device: it <i>is</i> the device-owner
 * component, so the name change means clear-then-re-set via the escape hatch in
 * {@link MainActivity}. Don't rename it casually.
 */
public class NexusDeviceAdminReceiver extends DeviceAdminReceiver {

    static final String TAG = "RoamNexus";

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
