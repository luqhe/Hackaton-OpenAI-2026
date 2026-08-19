package com.guardian.mobile

import android.app.Activity
import android.content.Context
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.concurrent.Executors

class GuardianController(
    private val activity: Activity,
) {
    private val preferences = activity.getSharedPreferences("guardian-mobile", Context.MODE_PRIVATE)
    private val executor = Executors.newSingleThreadExecutor()

    var apiUrl by mutableStateOf(preferences.getString("api_url", DEFAULT_API_URL) ?: DEFAULT_API_URL)
        private set
    var deviceId by mutableStateOf(preferences.getString("device_id", "device-demo") ?: "device-demo")
        private set
    var screen by mutableStateOf(GuardianScreen.DASHBOARD)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var notice by mutableStateOf<String?>(null)
        private set
    var incidents by mutableStateOf<List<Incident>>(emptyList())
        private set
    var selectedIncident by mutableStateOf<Incident?>(null)
        private set
    var report by mutableStateOf<DailyReport?>(null)
        private set
    var device by mutableStateOf<Device?>(null)
        private set
    var policies by mutableStateOf<List<PolicyRule>>(emptyList())
        private set
    var capabilities by mutableStateOf<ProductCapabilities?>(null)
        private set

    init {
        refreshDashboard()
    }

    fun open(screen: GuardianScreen) {
        this.screen = screen
        notice = null
        when (screen) {
            GuardianScreen.DASHBOARD -> refreshDashboard()
            GuardianScreen.CHILD -> refreshChild()
            GuardianScreen.POLICIES -> refreshPolicies()
            GuardianScreen.SETUP -> checkConnection()
            GuardianScreen.INCIDENT -> Unit
        }
    }

    fun refreshDashboard() = load {
        val api = GuardianApi(apiUrl)
        val nextIncidents = api.incidents()
        val nextReport = api.dailyReport()
        val nextCapabilities = api.capabilities()
        val fetchedDevice = runCatching { api.device(deviceId) }.getOrNull()
        val nextDevice = if (
            fetchedDevice != null && fetchedDevice.platform.equals("Android", ignoreCase = true)
        ) {
            runCatching { api.heartbeat(deviceId) }.getOrDefault(fetchedDevice)
        } else {
            fetchedDevice
        }
        onMain {
            incidents = nextIncidents
            report = nextReport
            capabilities = nextCapabilities
            device = nextDevice
        }
    }

    fun openIncident(incidentId: String) = load {
        val incident = GuardianApi(apiUrl).incident(incidentId)
        onMain {
            selectedIncident = incident
            screen = GuardianScreen.INCIDENT
        }
    }

    fun refreshChild() = load {
        val nextReport = GuardianApi(apiUrl).dailyReport()
        onMain { report = nextReport }
    }

    fun refreshPolicies() = load {
        val nextPolicies = GuardianApi(apiUrl).policy()
        onMain { policies = nextPolicies }
    }

    fun updatePolicy(category: String, action: String) {
        policies = policies.map { rule ->
            if (rule.category == category) rule.copy(action = action) else rule
        }
    }

    fun savePolicies() = load(successMessage = "Protection policies updated") {
        val saved = GuardianApi(apiUrl).replacePolicy(policies)
        onMain { policies = saved }
    }

    fun unlockSelected() {
        val id = selectedIncident?.id ?: return
        load(successMessage = "Unlock command sent") {
            val updated = GuardianApi(apiUrl).unlock(id)
            onMain { selectedIncident = updated }
        }
    }

    fun keepSelectedBlocked() {
        val id = selectedIncident?.id ?: return
        load(successMessage = "Block kept in place") {
            val updated = GuardianApi(apiUrl).keepBlocked(id)
            onMain { selectedIncident = updated }
        }
    }

    fun requestUnlock(explanation: String) {
        val id = selectedIncident?.id ?: return
        if (explanation.trim().length < 3) {
            error = "Add a short explanation before requesting review."
            return
        }
        load(successMessage = "Explanation sent to the parent view") {
            val updated = GuardianApi(apiUrl).requestUnlock(id, explanation.trim())
            onMain { selectedIncident = updated }
        }
    }

    fun saveApiUrl(value: String) {
        val normalized = value.trim().trimEnd('/')
        if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
            error = "The API URL must start with http:// or https://"
            return
        }
        apiUrl = normalized
        preferences.edit().putString("api_url", normalized).apply()
        checkConnection()
    }

    fun pairThisDevice() = load(successMessage = "Android device paired") {
        val api = GuardianApi(apiUrl)
        val name = "${Build.MANUFACTURER} ${Build.MODEL}".trim()
        val paired = api.pairDevice("child-demo", name)
        val activeDevice = runCatching { api.heartbeat(paired.id) }.getOrDefault(paired)
        onMain {
            deviceId = paired.id
            device = activeDevice
            preferences.edit().putString("device_id", paired.id).apply()
        }
    }

    fun useDemoDevice() {
        deviceId = "device-demo"
        preferences.edit().putString("device_id", deviceId).apply()
        refreshDashboard()
    }

    fun checkConnection() = load(successMessage = "Guardian API reachable") {
        val api = GuardianApi(apiUrl)
        api.health()
        val nextCapabilities = api.capabilities()
        onMain { capabilities = nextCapabilities }
    }

    fun clearMessages() {
        error = null
        notice = null
    }

    fun close() {
        executor.shutdownNow()
    }

    private fun load(
        successMessage: String? = null,
        block: () -> Unit,
    ) {
        loading = true
        error = null
        notice = null
        executor.execute {
            try {
                block()
                onMain {
                    loading = false
                    notice = successMessage
                }
            } catch (throwable: Throwable) {
                onMain {
                    loading = false
                    error = throwable.message ?: "Guardian could not complete the request."
                }
            }
        }
    }

    private fun onMain(block: () -> Unit) {
        activity.runOnUiThread(block)
    }

    companion object {
        // Android Emulator -> development machine loopback.
        const val DEFAULT_API_URL = "http://10.0.2.2:8000"
    }
}
