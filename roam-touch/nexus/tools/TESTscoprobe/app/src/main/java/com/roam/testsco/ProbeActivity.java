package com.roam.testsco;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * TEST ARTIFACT — a diagnostic, never shipped and never installed for longer than a run.
 * It decides whether the handset can capture audio AT ALL, by forcing the Bluetooth SCO (HFP)
 * route and comparing it against the built-in mic with the same source, in the same minute.
 *
 * ⚠️ It measures and prints LEVELS ONLY: RMS, peak, non-zero sample count. No audio is written
 * to disk, uploaded or retained — the PCM buffer is a local short[] that dies with the run.
 *
 * Build (the gradle wrapper is borrowed from nexus/, which is two levels up):
 *   cp -R ../../gradle ../../gradlew .   &&   echo sdk.dir=$ANDROID_HOME > local.properties
 *   ./gradlew assembleDebug
 * Run (the phone must be awake and unlocked; `wm dismiss-keyguard`):
 *   adb -s <dev> install -r -g app/build/outputs/apk/debug/app-debug.apk
 *   adb -s <dev> shell am start -n com.roam.testsco/.ProbeActivity
 *   adb -s <dev> shell am start -n com.roam.testsco/.ProbeActivity --ez vr_only true
 *   adb -s <dev> logcat -d | grep SCOPROBE          # and: grep -E 'select_devices|pcm_prepare'
 *   adb -s <dev> uninstall com.roam.testsco         # ALWAYS, in the same session
 *
 * ★ RESULT on sailfish, 2026-08-12 — the built-in mic is dead, capture in general is NOT.
 *   SCO + VOICE_RECOGNITION picked snd_device(70: bt-sco-mic-wb) and delivered 48640 frames,
 *   0 muted, 0 errors, peak -6.2 dBFS. EVERY snd_device on the built-in codec — handset-mic,
 *   speaker-mic, speaker-dmic-endfire, voice-rec-mic — fails `pcm_prepare` and returns pure
 *   zeroes. Same HAL, same ACDB, same app, same run: only the analog front end is broken.
 *
 * ⚠️ The source is a lever ONLY because this Qualcomm HAL derives the capture snd_device from
 * the OUTPUT device for MIC / VOICE_COMMUNICATION / DEFAULT — those three land back on
 * speaker-mic even with FOR_RECORD forced to BT SCO. VOICE_RECOGNITION is the one that
 * actually reaches bt-sco-mic-wb. Anything routing PTT through a headset must use it.
 */
public class ProbeActivity extends Activity {

    private static final String TAG = "SCOPROBE";
    private static final int RATE = 16000;
    private static final int RECORD_MS = 3000;

    private TextView view;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final StringBuilder log = new StringBuilder();

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        view = new TextView(this);
        view.setTextSize(14f);
        view.setTextColor(Color.WHITE);
        view.setBackgroundColor(Color.BLACK);
        view.setPadding(24, 48, 24, 24);
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(Color.BLACK);
        sv.addView(view);
        setContentView(sv);

        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO}, 1);
            say("waiting for RECORD_AUDIO permission…");
            return;
        }
        start();
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] p, int[] r) {
        if (r.length > 0 && r[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            start();
        } else {
            say("RECORD_AUDIO DENIED — probe cannot run");
        }
    }

    private void start() {
        new Thread(this::run, "probe").start();
    }

    private void say(String s) {
        Log.i(TAG, s);
        log.append(s).append('\n');
        ui.post(() -> view.setText(log.toString()));
    }

    // ------------------------------------------------------------------ run

    private void run() {
        AudioManager am = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        say("=== ROAM SCO PROBE ===");

        // `--ez vr_only true` runs only the same-source control: VOICE_RECOGNITION on the
        // built-in mic, no SCO. It is the direct counterpart of SCO/VOICE_RECOGNITION.
        if (getIntent() != null && getIntent().getBooleanExtra("vr_only", false)) {
            am.setMode(AudioManager.MODE_NORMAL);
            AudioDeviceInfo bi = null;
            for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_MIC) { bi = d; break; }
            }
            say("=== CONTROL: BUILTIN / VOICE_RECOGNITION, no SCO ===");
            record("BUILTIN/VOICE_RECOGNITION", MediaRecorder.AudioSource.VOICE_RECOGNITION,
                    bi, am);
            say("=== PROBE DONE ===");
            return;
        }
        say("scoAvailableOffCall=" + am.isBluetoothScoAvailableOffCall()
                + " micMute=" + am.isMicrophoneMute()
                + " mode=" + am.getMode());

        AudioDeviceInfo sco = null;
        say("-- input devices --");
        for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
            say("   type=" + d.getType() + " " + typeName(d.getType())
                    + " name=" + d.getProductName() + " id=" + d.getId());
            if (d.getType() == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) sco = d;
        }

        // ---------------------------------------------------------- phase A
        say("");
        say("=== PHASE A: BLUETOOTH SCO (HFP) ===");
        if (sco == null) {
            say("NOTE: no TYPE_BLUETOOTH_SCO input device listed yet (normal before SCO is up)");
        }

        final CountDownLatch connected = new CountDownLatch(1);
        BroadcastReceiver rx = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent i) {
                int st = i.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -99);
                say("   SCO_AUDIO_STATE -> " + scoName(st));
                if (st == AudioManager.SCO_AUDIO_STATE_CONNECTED) connected.countDown();
            }
        };
        registerReceiver(rx, new IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED));

        boolean scoUp = false;
        try {
            am.setMode(AudioManager.MODE_IN_COMMUNICATION);
            say("setMode(MODE_IN_COMMUNICATION) -> mode=" + am.getMode());
            am.startBluetoothSco();
            say("startBluetoothSco() issued, waiting up to 12 s…");
            scoUp = connected.await(12, TimeUnit.SECONDS);
            if (!scoUp) {
                say("no CONNECTED after 12 s — retrying once");
                am.stopBluetoothSco();
                Thread.sleep(1000);
                am.startBluetoothSco();
                scoUp = connected.await(12, TimeUnit.SECONDS);
            }
            if (scoUp) {
                am.setBluetoothScoOn(true);
                say("SCO CONNECTED. setBluetoothScoOn(true) -> isBluetoothScoOn="
                        + am.isBluetoothScoOn());
                Thread.sleep(500);
                // re-enumerate now that SCO is up
                for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                    if (d.getType() == AudioDeviceInfo.TYPE_BLUETOOTH_SCO) {
                        sco = d;
                        say("   SCO input now present: id=" + d.getId()
                                + " name=" + d.getProductName());
                    }
                }
                // The Qualcomm HAL derives the capture snd_device from the OUTPUT device for
                // AUDIO_SOURCE_VOICE_COMMUNICATION, which is why that source alone can land on
                // speaker-mic even with SCO forced. Sweep the sources so at least one is
                // guaranteed to hit bt-sco-mic.
                int[] sources = {
                        MediaRecorder.AudioSource.MIC,
                        MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                        MediaRecorder.AudioSource.VOICE_RECOGNITION,
                        MediaRecorder.AudioSource.DEFAULT,
                };
                String[] names = {"MIC", "VOICE_COMMUNICATION", "VOICE_RECOGNITION", "DEFAULT"};
                for (int i = 0; i < sources.length; i++) {
                    say("");
                    record("SCO/" + names[i], sources[i], sco, am);
                    Thread.sleep(800);
                }
            } else {
                say("RESULT: SCO NEVER CONNECTED — cannot test the headset mic.");
                say("        (is the headset powered on and connected?)");
            }
        } catch (Exception e) {
            say("phase A exception: " + e);
        } finally {
            try {
                am.setBluetoothScoOn(false);
                am.stopBluetoothSco();
                unregisterReceiver(rx);
            } catch (Exception ignored) {
            }
        }

        // ---------------------------------------------------------- phase B
        try {
            Thread.sleep(1500);
        } catch (InterruptedException ignored) {
        }
        say("");
        say("=== PHASE B: BUILT-IN MIC (control) ===");
        am.setMode(AudioManager.MODE_NORMAL);
        AudioDeviceInfo builtin = null;
        for (AudioDeviceInfo d : am.getDevices(AudioManager.GET_DEVICES_INPUTS)) {
            if (d.getType() == AudioDeviceInfo.TYPE_BUILTIN_MIC) {
                builtin = d;
                break;
            }
        }
        record("BUILTIN/MIC", MediaRecorder.AudioSource.MIC, builtin, am);
        try {
            Thread.sleep(800);
        } catch (InterruptedException ignored) {
        }
        record("BUILTIN/VOICE_COMMUNICATION", MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                builtin, am);

        am.setMode(AudioManager.MODE_NORMAL);
        say("");
        say("=== PROBE DONE ===");
    }

    // --------------------------------------------------------------- record

    private void record(String label, int source, AudioDeviceInfo prefer, AudioManager am) {
        int minBuf = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT);
        int buf = Math.max(minBuf * 4, RATE * 2);
        AudioRecord ar = null;
        try {
            ar = new AudioRecord(source, RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, buf);
            if (ar.getState() != AudioRecord.STATE_INITIALIZED) {
                say(label + ": AudioRecord failed to initialise");
                return;
            }
            if (prefer != null) {
                boolean ok = ar.setPreferredDevice(prefer);
                say(label + ": setPreferredDevice(type=" + prefer.getType() + ") -> " + ok);
            }
            ar.startRecording();
            AudioDeviceInfo routed = ar.getRoutedDevice();
            say(label + ": routedDevice="
                    + (routed == null ? "null" : routed.getType() + " " + typeName(routed.getType())
                    + " / " + routed.getProductName()));

            short[] chunk = new short[1024];
            long frames = 0, nonZero = 0, sumSq = 0;
            int peak = 0;
            long t0 = System.nanoTime();
            long deadline = t0 + RECORD_MS * 1_000_000L;
            int reads = 0, errs = 0;
            while (System.nanoTime() < deadline) {
                int n = ar.read(chunk, 0, chunk.length);
                if (n < 0) {
                    errs++;
                    break;
                }
                reads++;
                for (int i = 0; i < n; i++) {
                    short s = chunk[i];
                    if (s != 0) nonZero++;
                    int a = Math.abs(s);
                    if (a > peak) peak = a;
                    sumSq += (long) s * s;
                }
                frames += n;
            }
            long wallMs = (System.nanoTime() - t0) / 1_000_000L;
            ar.stop();

            double audioMs = frames * 1000.0 / RATE;
            double live = wallMs == 0 ? 0 : audioMs / wallMs;
            double rms = frames == 0 ? 0 : Math.sqrt((double) sumSq / frames);
            double rmsDb = rms <= 0 ? Double.NEGATIVE_INFINITY : 20 * Math.log10(rms / 32768.0);
            double peakDb = peak <= 0 ? Double.NEGATIVE_INFINITY : 20 * Math.log10(peak / 32768.0);

            say(label + ": frames=" + frames + " (" + String.format("%.0f", audioMs)
                    + " ms audio in " + wallMs + " ms wall, live=" + String.format("%.2f", live) + ")");
            say(label + ": reads=" + reads + " errs=" + errs + " minBuf=" + minBuf + " buf=" + buf);
            say(label + ": nonZeroSamples=" + nonZero + " / " + frames
                    + "  (" + String.format("%.2f", frames == 0 ? 0 : 100.0 * nonZero / frames) + " %)");
            say(label + ": peak=" + peak + " (" + fmtDb(peakDb) + " dBFS)  rms="
                    + String.format("%.1f", rms) + " (" + fmtDb(rmsDb) + " dBFS)");
            say(label + ": VERDICT " + (nonZero > 0 && peak > 4 ? "*** CAPTURE WORKS ***"
                    : "SILENCE — no signal"));
        } catch (Exception e) {
            say(label + ": exception " + e);
        } finally {
            if (ar != null) {
                try {
                    ar.release();
                } catch (Exception ignored) {
                }
            }
        }
    }

    private static String fmtDb(double d) {
        return Double.isInfinite(d) ? "-inf" : String.format("%.1f", d);
    }

    private static String scoName(int s) {
        switch (s) {
            case AudioManager.SCO_AUDIO_STATE_CONNECTED: return "CONNECTED";
            case AudioManager.SCO_AUDIO_STATE_CONNECTING: return "CONNECTING";
            case AudioManager.SCO_AUDIO_STATE_DISCONNECTED: return "DISCONNECTED";
            case AudioManager.SCO_AUDIO_STATE_ERROR: return "ERROR";
            default: return "?" + s;
        }
    }

    private static String typeName(int t) {
        switch (t) {
            case AudioDeviceInfo.TYPE_BUILTIN_MIC: return "BUILTIN_MIC";
            case AudioDeviceInfo.TYPE_BLUETOOTH_SCO: return "BLUETOOTH_SCO";
            case AudioDeviceInfo.TYPE_BLUETOOTH_A2DP: return "BLUETOOTH_A2DP";
            case AudioDeviceInfo.TYPE_WIRED_HEADSET: return "WIRED_HEADSET";
            case AudioDeviceInfo.TYPE_TELEPHONY: return "TELEPHONY";
            case AudioDeviceInfo.TYPE_FM_TUNER: return "FM_TUNER";
            case AudioDeviceInfo.TYPE_USB_DEVICE: return "USB_DEVICE";
            case AudioDeviceInfo.TYPE_USB_HEADSET: return "USB_HEADSET";
            default: return "type" + t;
        }
    }
}
