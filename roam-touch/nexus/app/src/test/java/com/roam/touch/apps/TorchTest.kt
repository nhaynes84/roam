package com.roam.touch.apps

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Which camera's flash the torch drives.
 *
 * ★ Kept as a pure function over the ids so the "never hard-code 0" rule is covered
 * without a camera, exactly the way [isLaunchableUrl] covers the URL rule without an
 * Activity. The home screen is the one place where a wrong assumption costs the whole
 * device its UI, so these rules do not get to live only on the device.
 */
class TorchTest {

    @Test
    fun `it picks the first camera that actually reports a flash`() {
        // ⚠️ The back camera is *usually* id 0 and usually the one with the flash. This is
        // the device where it is not: hard-coding "0" would drive a camera with no flash
        // and fail silently at the tap.
        val ids = listOf("0", "1", "2")
        assertEquals("1", Torch.pick(ids) { it == "1" })
    }

    @Test
    fun `no camera with a flash is null, not a guess`() {
        assertNull(Torch.pick(listOf("0", "1")) { false })
        assertNull(Torch.pick(emptyList()) { true })
    }

    @Test
    fun `a camera that throws when asked is skipped, not propagated`() {
        // ⚠️ getCameraCharacteristics throws CameraAccessException for a camera that has
        // been disconnected. On the app shelf that must cost one camera, never the screen:
        // this is the only route off a device-owner home screen.
        val ids = listOf("0", "1")
        val picked = Torch.pick(ids) { id ->
            if (id == "0") throw IllegalStateException("camera went away") else true
        }
        assertEquals("1", picked)
    }

    @Test
    fun `every camera throwing is null, still not a crash`() {
        assertNull(Torch.pick(listOf("0", "1")) { throw IllegalStateException("gone") })
    }

    @Test
    fun `the order asked is the order given`() {
        // The system's own ordering is the answer; nothing here re-sorts it.
        assertEquals("2", Torch.pick(listOf("2", "0", "1")) { it != "0" })
    }
}
