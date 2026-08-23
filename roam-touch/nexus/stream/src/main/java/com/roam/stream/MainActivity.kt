package com.roam.stream

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
import com.roam.touch.channels.net.HubConfig
import java.net.URI

class MainActivity : ComponentActivity() {

    private lateinit var vm: StreamViewModel

    private val askMic = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> vm.onMicPermission(granted) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val uri = URI(BuildConfig.HUB_URL)
        val config = HubConfig(
            host = uri.host ?: "100.67.237.109",
            port = if (uri.port > 0) uri.port else 8787,
            token = BuildConfig.HUB_TOKEN,
        )
        // ★ A stable per-install name so the hub (and he) can tell devices apart in
        //   the floor snapshot. Model, not a random id: "Pixel 11" means something
        //   when it is the thing holding the channel open.
        val device = (Build.MODEL ?: "android").replace(' ', '-')

        vm = ViewModelProvider(
            this,
            viewModelFactory { initializer { StreamViewModel(config, device) } },
        )[StreamViewModel::class.java]

        vm.onMicPermission(
            ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                    == PackageManager.PERMISSION_GRANTED
        )

        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                val ui by vm.ui.collectAsState()
                StreamScreen(
                    ui = ui,
                    onRole = { role ->
                        // Ask only when a role actually needs the mic — a receiver
                        // that never talks back should not be prompted at all.
                        if (role != Role.OFF && !ui.micGranted) {
                            askMic.launch(Manifest.permission.RECORD_AUDIO)
                        }
                        vm.setRole(role)
                    },
                    onPress = vm::press,
                    onRelease = vm::release,
                )
            }
        }
    }
}
