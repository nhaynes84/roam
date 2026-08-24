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
        /** Old hardware: small and slow, because it runs hot under sustained load. */
        val MODEST = VideoProfile(480, 360, 2, 60)

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
    fun start(onFrame: (ByteArray) -> Unit): String? {
        if (running) return null
        if (!hasPermission()) return "camera permission not granted"
        return runCatching { open(onFrame); null }
            .getOrElse { "${it::class.simpleName}: ${it.message}" }
    }

    @SuppressLint("MissingPermission")
    private fun open(onFrame: (ByteArray) -> Unit) {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = pickCamera(manager)
            ?: throw IllegalStateException("no usable camera on this device")

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
                camera = device
                val request = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                    .apply {
                        addTarget(r.surface)
                        set(CaptureRequest.JPEG_QUALITY, profile.quality.toByte())
                        set(
                            CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE,
                            android.util.Range(profile.fps, profile.fps)
                        )
                    }
                @Suppress("DEPRECATION")
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
            }

            override fun onDisconnected(device: CameraDevice) = stop()
            override fun onError(device: CameraDevice, error: Int) = stop()
        }, h)
        running = true
    }

    /** Back camera by preference — a worn build points its lens away from him. */
    private fun pickCamera(manager: CameraManager): String? {
        val ids = runCatching { manager.cameraIdList }.getOrDefault(emptyArray())
        val back = ids.firstOrNull {
            runCatching {
                manager.getCameraCharacteristics(it)
                    .get(CameraCharacteristics.LENS_FACING)
            }.getOrNull() == CameraCharacteristics.LENS_FACING_BACK
        }
        return back ?: ids.firstOrNull()
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
