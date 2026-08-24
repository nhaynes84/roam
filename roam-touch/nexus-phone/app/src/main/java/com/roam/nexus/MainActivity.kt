package com.roam.nexus

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.roam.touch.stream.Role
import com.roam.touch.stream.StreamViewModel
import com.roam.touch.channels.net.HubApi

class MainActivity : ComponentActivity() {

    private lateinit var nexus: NexusViewModel
    private lateinit var stream: StreamViewModel

    private val askMic = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> stream.onMicPermission(granted) }

    // ⚠️ Its own request: a camera is a bigger ask than a microphone.
    private val askCamera = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val config = NexusViewModel.config()
        // ★ The model, not a random id: "Pixel-11-Pro-XL" means something in a floor
        //   snapshot when it is the thing holding the channel open.
        val device = (Build.MODEL ?: "android").replace(' ', '-')

        val factory = viewModelFactory {
            initializer { NexusViewModel(HubApi(config)) }
            initializer { StreamViewModel(config, device, video = com.roam.touch.stream.StreamVideo(applicationContext)) }
        }
        val provider = ViewModelProvider(this, factory)
        nexus = provider[NexusViewModel::class.java]
        stream = provider[StreamViewModel::class.java]

        stream.onMicPermission(
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                    == PackageManager.PERMISSION_GRANTED
        )

        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                val ui by nexus.ui.collectAsState()
                val su by stream.ui.collectAsState()
                NexusApp(
                    channels = ui.channels,
                    thread = ui.thread,
                    openPane = ui.openPane,
                    connected = ui.connected,
                    streamUi = su,
                    onOpen = nexus::open,
                    onSend = nexus::send,
                    onRole = { role ->
                        // Only ask when a role actually needs the mic — a receiver
                        // that never talks back should not be prompted at all.
                        if (role != Role.OFF && !su.micGranted) {
                            askMic.launch(Manifest.permission.RECORD_AUDIO)
                        }
                        stream.setRole(role)
                    },
                    onPress = stream::press,
                    onRelease = stream::release,
                    onVideo = { on ->
                        if (on && !su.videoOut) askCamera.launch(Manifest.permission.CAMERA)
                        stream.setVideo(on)
                    },
                )
            }
        }
    }
}
