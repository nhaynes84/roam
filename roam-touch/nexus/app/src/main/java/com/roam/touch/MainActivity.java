package com.roam.touch;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.view.KeyEvent;
import android.util.Log;

import androidx.activity.ComponentActivity;

import com.roam.touch.channels.HubService;
import com.roam.touch.channels.Roam;
import com.roam.touch.channels.ui.ChannelsAppKt;
import com.roam.touch.channels.ui.SystemBars;

/**
 * Nexus — the ROAM home screen. It owns two separable jobs and keeps them separable:
 *
 * <ol>
 *   <li><b>Device policy.</b> Device-owner status, the persistent home registration and
 *       the escape hatch. All of it below, all of it unchanged from the shell version.
 *   <li><b>Channels.</b> The actual UI, which lives entirely in
 *       {@code com.roam.touch.channels} and is attached here in one line.
 * </ol>
 *
 * <p>⚠️ This class extends {@code ComponentActivity} rather than {@code Activity} only
 * because Compose needs a {@code LifecycleOwner} and a {@code SavedStateRegistryOwner}.
 * The component name {@code com.roam.touch/.MainActivity} is unchanged, so neither the
 * device-owner grant nor the pinned home activity is affected — both key on the name.
 *
 * <p><b>Not a kiosk.</b> The normal Android base stays: notification shade, Settings and
 * recents all remain reachable. No lock-task, no hidden launcher, no stripped SystemUI —
 * Settings is the "we broke something, unfuck it" path and must never be sealed off.
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
public class MainActivity extends ComponentActivity {

    /** Boolean intent extra; when true, the app gives up device-owner status. */
    public static final String EXTRA_CLEAR_DEVICE_OWNER = "clear_device_owner";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());

        // ★ The stock status bar comes off — 24 dp of a 411 dp landscape window, spent
        // permanently on a second battery readout and other apps' notification icons.
        // See SystemBars for what it costs and what it deliberately leaves alone.
        SystemBars.hideStatusBar(this);

        // The connection, the socket and the voice outlive this Activity: the launcher
        // is torn down and rebuilt constantly, and an outcome landing while the screen
        // is off still has to be heard. HubService owns all of it.
        Roam.INSTANCE.init(this);
        HubService.Companion.start(this);
        ChannelsAppKt.installChannelsUi(this);
    }

    /**
     * ⚠️ Load-bearing, not cosmetic. Hiding the status bar is a flag on this window, and
     * every other window that takes focus — the notification shade, a permission dialog,
     * Settings — hands focus back with that flag cleared. Without this the bar comes back
     * the first time he pulls the shade down and never leaves again, which is precisely
     * the state being fixed.
     */
    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            SystemBars.hideStatusBar(this);
        } else {
            // The release edge will never arrive if focus goes while he is holding.
            Roam.INSTANCE.getControls().onFocusLost();
        }
    }

    /**
     * ★★ Volume-down is push-to-talk: tap for volume, hold to talk.
     *
     * It is intercepted here rather than in Compose because a hardware key is the only
     * input on this device that reports a real held state -- see VolumePtt for why the
     * earbud and the wired inline button both cannot. Volume-up is never touched.
     */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (Roam.INSTANCE.getControls().onVolumeKey(event)) {
            return true;
        }
        return super.dispatchKeyEvent(event);
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
        if (owner) {
            setAsPersistentHome(dpm, pkg);
            grantMicrophone(dpm);
        }

        // No longer painted on screen — the panel belongs to Channels. logcat is where
        // this is checked from now on:  adb logcat -s RoamNexus
        Log.i(NexusDeviceAdminReceiver.TAG, "device owner = " + owner);
    }

    /**
     * Make Home always land on Nexus, with no "pick a launcher" dialog.
     *
     * <p>Only a device owner may do this. The stock Pixel launcher stays installed as a
     * fallback and is still reachable once this preference is cleared — which the escape
     * hatch does, so there is always a way back to a working home screen.
     */
    private void setAsPersistentHome(DevicePolicyManager dpm, String pkg) {
        try {
            IntentFilter home = new IntentFilter(Intent.ACTION_MAIN);
            home.addCategory(Intent.CATEGORY_HOME);
            home.addCategory(Intent.CATEGORY_DEFAULT);
            dpm.addPersistentPreferredActivity(
                    new ComponentName(this, NexusDeviceAdminReceiver.class),
                    home,
                    new ComponentName(this, MainActivity.class));
            Log.i(NexusDeviceAdminReceiver.TAG, "registered as persistent home");
        } catch (Exception e) {
            Log.e(NexusDeviceAdminReceiver.TAG, "addPersistentPreferredActivity failed", e);
        }
    }

    /**
     * Grant ourselves {@code RECORD_AUDIO}, which only a device owner may do.
     *
     * <p>Push to talk is the input half of this device. A runtime permission dialog on
     * a screen strapped to a forearm is a bad first press — worse, it appears
     * <i>after</i> the thumb is already down and the sentence has started. Device owner
     * exists precisely to answer this in advance, so it does.
     *
     * <p>⚠️ This grants the permission; it does not open a microphone. The mic is opened
     * by {@code MicRecorder} from exactly one place, a press on the PTT control, and is
     * closed on release. There is no wake word and no background listening.
     *
     * <p>⚠️ Wrapped, like every other policy call here: a failure must cost a permission
     * dialog, never the home screen. On a non-owner build (the emulator) this never
     * runs and the normal runtime request in {@code ChannelsApp} handles it.
     */
    private void grantMicrophone(DevicePolicyManager dpm) {
        try {
            dpm.setPermissionGrantState(
                    new ComponentName(this, NexusDeviceAdminReceiver.class),
                    getPackageName(),
                    android.Manifest.permission.RECORD_AUDIO,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
            Log.i(NexusDeviceAdminReceiver.TAG, "microphone granted by policy");
        } catch (Exception e) {
            Log.e(NexusDeviceAdminReceiver.TAG, "setPermissionGrantState failed", e);
        }
    }

    /**
     * Give up device owner, and the home registration with it.
     *
     * <p>⚠️ Order matters: clearing the persistent preferred activity needs device-owner
     * privilege, so it has to happen <i>before</i> {@code clearDeviceOwnerApp}. Getting
     * this backwards would strand Home on a Nexus that can no longer unregister itself.
     *
     * <p>⚠️ Measured on sailfish 2026-08-11: this drops the persistent-preferred record,
     * but Home resolution can still land on Nexus afterwards. That is not a dead end —
     * adb restores the stock launcher without any device-owner privilege:
     *
     * <pre>adb shell cmd package set-home-activity \
     *     com.google.android.apps.nexuslauncher/.NexusLauncherActivity</pre>
     *
     * Verified working. Keep nexuslauncher installed so that command always has a target.
     */
    private void clearDeviceOwner(DevicePolicyManager dpm, String pkg) {
        if (dpm == null || !dpm.isDeviceOwnerApp(pkg)) {
            Log.w(NexusDeviceAdminReceiver.TAG, "clear requested but not device owner");
            return;
        }
        try {
            dpm.clearPackagePersistentPreferredActivities(
                    new ComponentName(this, NexusDeviceAdminReceiver.class), pkg);
            Log.i(NexusDeviceAdminReceiver.TAG, "home registration cleared");
        } catch (Exception e) {
            Log.e(NexusDeviceAdminReceiver.TAG, "clearPersistentPreferred failed", e);
        }
        try {
            dpm.clearDeviceOwnerApp(pkg);
            Log.i(NexusDeviceAdminReceiver.TAG, "device owner cleared");
        } catch (Exception e) {
            Log.e(NexusDeviceAdminReceiver.TAG, "clearDeviceOwnerApp failed", e);
        }
    }
}
