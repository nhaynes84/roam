package com.roam.touch.stream

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import androidx.core.content.ContextCompat

/**
 * The camera, as low as it will go.
 *
 * ★ JPEG straight out of the ImageReader, which on Android is produced by the ISP —
 * dedicated silicon, not the CPU. That is the same reason a video call runs acceptably
 * on a phone from 2016: the expensive part was never compression, it is doing
 * compression in software. Nothing here touches a pixel on the CPU.
 *
 * ⚠️ Per-device settings, because the three machines are not the same machine. The
 * transport is identical either way — only the numbers differ.
 */
data class VideoProfile(val width: Int, val height: Int, val fps: Int, val quality: Int) {
    val frameIntervalMs: Long get() = 1000L / fps.coerceAtLeast(1)

    companion object {
        /** Old hardware: a smaller FRAME, not a slower one.
         *  ⚠️ Was 2 fps and he said flatly it is too low. Resolution is what costs the
         *  ISP and the link; frame rate is what makes it look like a video call. Drop
         *  the pixels, keep the motion. */
        val MODEST = VideoProfile(480, 360, 6, 60)

        /** Anything current. */
        val NORMAL = VideoProfile(640, 480, 6, 70)

        /**
         * ⚠️ Chosen by MODEL, not by benchmark. A benchmark on a cold phone says
         * nothing about the same phone twenty minutes into a stream.
         */
        fun forThisDevice(): VideoProfile =
            if ((Build.MODEL ?: "").trim().equals("Pixel", ignoreCase = true)) MODEST
            else NORMAL
    }
}

class StreamVideo(private val context: Context) {

    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null

    @Volatile private var lastSentAt = 0L
    @Volatile private var running = false

    val profile: VideoProfile = VideoProfile.forThisDevice()

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED

    /**
     * @param onFrame a complete JPEG. Called on the camera thread, never the main one —
     *   same rule as audio, for the same reason.
     * @return null on success, or why it failed.
     */
    fun start(facing: String, onFrame: (ByteArray) -> Unit): String? {
        if (running) return null
        if (!hasPermission()) return "camera permission not granted"
        return runCatching { open(facing, onFrame); null }
            .getOrElse { "${it::class.simpleName}: ${it.message}" }
    }

    /** Switching lens means a full reopen — a camera device serves one lens. */
    fun switchTo(facing: String, onFrame: (ByteArray) -> Unit): String? {
        stop()
        return start(facing, onFrame)
    }

    @SuppressLint("MissingPermission")
    private fun open(facing: String, onFrame: (ByteArray) -> Unit) {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = pickCamera(manager, facing)
            ?: throw IllegalStateException("no $facing camera on this device")
        val sensorOrientation = runCatching {
            manager.getCameraCharacteristics(id)
                .get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0
        }.getOrDefault(0)

        val t = HandlerThread("stream-video").also { it.start() }
        thread = t
        val h = Handler(t.looper)
        handler = h

        val r = ImageReader.newInstance(profile.width, profile.height, ImageFormat.JPEG, 2)
        reader = r
        r.setOnImageAvailableListener({ ir ->
            val image = ir.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                // ⚠️ Rate-limit HERE rather than trusting the requested fps range:
                //    Camera2 honours it loosely, and dropping a frame we do not need
                //    costs nothing while keeping the pipeline warm.
                val now = System.currentTimeMillis()
                if (now - lastSentAt >= profile.frameIntervalMs) {
                    lastSentAt = now
                    val buf = image.planes[0].buffer
                    val bytes = ByteArray(buf.remaining())
                    buf.get(bytes)
                    onFrame(bytes)
                }
            } finally {
                // ⚠️ An unclosed Image stalls the reader dead after 2 frames.
                image.close()
            }
        }, h)

        manager.openCamera(id, object : CameraDevice.StateCallback() {
            override fun onOpened(device: CameraDevice) {
                // ⚠️⚠️ THE CALLBACK CAN ARRIVE AFTER TEARDOWN. stop() closes the camera,
                //    and if that happened between openCamera() and this callback the
                //    device is already dead — createCaptureSession then throws
                //    "CameraDevice was already closed" ON THE CAMERA THREAD, uncaught,
                //    and the app dies. Toggling video off quickly, or switchTo()'s
                //    stop-then-start, is enough to hit it.
                //    Same rule the audio read/write paths already follow: anything that
                //    can land after teardown must tolerate landing after teardown.
                if (!running) {
                    runCatching { device.close() }
                    return
                }
                camera = device
                val request = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                    .apply {
                        addTarget(r.surface)
                        set(CaptureRequest.JPEG_QUALITY, profile.quality.toByte())
                        // ⚠️ Without this the JPEG comes out in SENSOR orientation,
                        //    which on a phone is 90° off — "you are rotating the
                        //    phones video 90 cw". The sensor is mounted rotated; the
                        //    ISP will correct it, but only if asked.
                        set(CaptureRequest.JPEG_ORIENTATION, sensorOrientation)
                        // ⚠️ Only if the device actually offers it. A fixed [6,6]
                        //    range is not universal on older camera HALs, and an
                        //    unsupported range throws rather than being ignored. We
                        //    rate-limit on receipt anyway, so this is an optimisation,
                        //    never a requirement.
                        supportedFpsRange(manager, id, profile.fps)?.let {
                            set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, it)
                        }
                    }
                @Suppress("DEPRECATION")
                runCatching {
                device.createCaptureSession(
                    listOf(r.surface),
                    object : CameraCaptureSession.StateCallback() {
                        override fun onConfigured(s: CameraCaptureSession) {
                            session = s
                            runCatching { s.setRepeatingRequest(request.build(), null, h) }
                        }

                        override fun onConfigureFailed(s: CameraCaptureSession) = Unit
                    },
                    h,
                )
                }.onFailure { stop() }
            }

            override fun onDisconnected(device: CameraDevice) = stop()
            override fun onError(device: CameraDevice, error: Int) = stop()
        }, h)
        running = true
    }

    /** The device's own range covering our target, or null to leave it alone. */
    private fun supportedFpsRange(
        manager: CameraManager, id: String, fps: Int
    ): android.util.Range<Int>? = runCatching {
        val ranges = manager.getCameraCharacteristics(id)
            .get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)
        ranges?.firstOrNull { it.lower <= fps && fps <= it.upper }
    }.getOrNull()

    /**
     * The requested lens, falling back to whatever exists.
     * ⚠️ Falls back rather than failing: a device with one camera should still show a
     * picture when someone asks for the other one.
     */
    private fun pickCamera(manager: CameraManager, facing: String): String? {
        val want = if (facing == "front") CameraCharacteristics.LENS_FACING_FRONT
                   else CameraCharacteristics.LENS_FACING_BACK
        val ids = runCatching { manager.cameraIdList }.getOrDefault(emptyArray())
        val match = ids.firstOrNull {
            runCatching {
                manager.getCameraCharacteristics(it)
                    .get(CameraCharacteristics.LENS_FACING)
            }.getOrNull() == want
        }
        return match ?: ids.firstOrNull()
    }

    fun stop() {
        running = false
        runCatching { session?.stopRepeating() }
        runCatching { session?.close() }
        session = null
        runCatching { camera?.close() }
        camera = null
        runCatching { reader?.close() }
        reader = null
        runCatching { thread?.quitSafely() }
        thread = null
        handler = null
    }
}
