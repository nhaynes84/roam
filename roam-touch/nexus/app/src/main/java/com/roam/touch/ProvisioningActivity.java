package com.roam.touch;

import android.app.Activity;
import android.app.admin.DevicePolicyManager;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;

/**
 * Handles the two hooks managed provisioning calls on a DPC from API 29 onwards:
 * {@code ACTION_GET_PROVISIONING_MODE} and {@code ACTION_ADMIN_POLICY_COMPLIANCE}.
 *
 * <p>Unused on this device — device owner here is set by {@code adb shell dpm
 * set-device-owner}, not by QR or NFC provisioning. It exists so that path is open
 * later without touching the manifest again.
 */
public class ProvisioningActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        String action = getIntent() == null ? null : getIntent().getAction();
        Log.i(NexusDeviceAdminReceiver.TAG, "provisioning activity: " + action);

        if (DevicePolicyManager.ACTION_GET_PROVISIONING_MODE.equals(action)) {
            // Fully managed device, never a work profile.
            Intent result = new Intent();
            result.putExtra(
                    DevicePolicyManager.EXTRA_PROVISIONING_MODE,
                    DevicePolicyManager.PROVISIONING_MODE_FULLY_MANAGED_DEVICE);
            setResult(RESULT_OK, result);
        } else {
            // ACTION_ADMIN_POLICY_COMPLIANCE: nothing to enforce yet.
            setResult(RESULT_OK);
        }
        finish();
    }
}
