package com.guardian.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    private lateinit var controller: GuardianController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        controller = GuardianController(this)
        setContent {
            GuardianMobileTheme {
                GuardianMobileApp(controller)
            }
        }
    }

    override fun onDestroy() {
        controller.close()
        super.onDestroy()
    }
}
