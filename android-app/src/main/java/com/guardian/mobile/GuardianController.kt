package com.guardian.mobile

import android.app.Activity
import android.content.Context
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
    var demoMode by mutableStateOf(preferences.getBoolean("demo_mode", false))
        private set
    var childId by mutableStateOf(preferences.getString("child_id", "child-demo") ?: "child-demo")
        private set
    var deviceId by mutableStateOf(preferences.getString("device_id", "") ?: "")
        private set
    var screen by mutableStateOf(if (demoMode) GuardianScreen.DASHBOARD else GuardianScreen.LOGIN)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set
    var notice by mutableStateOf<String?>(null)
        private set
    var isAuthenticated by mutableStateOf(demoMode)
        private set
    var session by mutableStateOf<GuardianSession?>(null)
        private set
    var pairingChallenge by mutableStateOf<PairingChallenge?>(null)
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

    private var api = GuardianApi(apiUrl, demoMode)

    init {
        if (demoMode) refreshDashboard() else checkConnection()
    }

    fun open(target: GuardianScreen) {
        if (!demoMode && !isAuthenticated && target !in setOf(GuardianScreen.LOGIN, GuardianScreen.SETUP)) {
            screen = GuardianScreen.LOGIN
            return
        }
        screen = target
        notice = null
        when (target) {
            GuardianScreen.LOGIN -> Unit
            GuardianScreen.DASHBOARD -> refreshDashboard()
            GuardianScreen.CHILD -> refreshChild()
            GuardianScreen.POLICIES -> refreshPolicies()
            GuardianScreen.SETUP -> checkConnection()
            GuardianScreen.INCIDENT -> Unit
        }
    }

    fun login(email: String, password: String, familyId: String?) = load(successMessage = "Sessão iniciada") {
        val nextSession = api.login(email, password, familyId)
        onMain {
            session = nextSession
            isAuthenticated = true
            screen = GuardianScreen.DASHBOARD
        }
        val snapshot = fetchDashboardSnapshot()
        onMain { applyDashboardSnapshot(snapshot) }
    }

    fun logout() {
        loading = true
        error = null
        notice = null
        executor.execute {
            runCatching { api.logout() }
            onMain {
                session = null
                isAuthenticated = false
                pairingChallenge = null
                incidents = emptyList()
                report = null
                device = null
                policies = emptyList()
                selectedIncident = null
                loading = false
                notice = "Sessão encerrada"
                screen = GuardianScreen.LOGIN
            }
        }
    }

    fun refreshDashboard() = load {
        val snapshot = fetchDashboardSnapshot()
        onMain {
            isAuthenticated = true
            applyDashboardSnapshot(snapshot)
        }
    }

    fun openIncident(incidentId: String) = load {
        val incident = api.incident(incidentId)
        onMain {
            selectedIncident = incident
            screen = GuardianScreen.INCIDENT
        }
    }

    fun refreshChild() = load {
        val nextReport = api.dailyReport(childId)
        val nextIncidents = api.incidents(childId)
        onMain {
            report = nextReport
            incidents = nextIncidents
        }
    }

    fun refreshPolicies() = load {
        val nextPolicies = api.policy(childId)
        onMain { policies = nextPolicies }
    }

    fun updatePolicy(category: String, action: String) {
        policies = policies.map { rule ->
            if (rule.category == category) rule.copy(action = action) else rule
        }
    }

    fun savePolicies() = load(successMessage = "Políticas atualizadas") {
        val saved = api.replacePolicy(policies, childId)
        onMain { policies = saved }
    }

    fun unlockSelected() {
        val id = selectedIncident?.id ?: return
        load(successMessage = "Comando de desbloqueio enviado") {
            val updated = api.unlock(id)
            onMain { selectedIncident = updated }
        }
    }

    fun keepSelectedBlocked() {
        val id = selectedIncident?.id ?: return
        load(successMessage = "Bloqueio mantido") {
            val updated = api.keepBlocked(id)
            onMain { selectedIncident = updated }
        }
    }

    fun requestUnlock(explanation: String) {
        val id = selectedIncident?.id ?: return
        if (explanation.trim().length < 3) {
            error = "Adicione uma explicação curta antes de solicitar revisão."
            return
        }
        load(successMessage = "Explicação enviada") {
            val updated = api.requestUnlock(id, explanation.trim())
            onMain { selectedIncident = updated }
        }
    }

    fun saveApiUrl(value: String) {
        val normalized = value.trim().trimEnd('/')
        if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
            error = "A URL da API deve começar com http:// ou https://"
            return
        }
        apiUrl = normalized
        preferences.edit().putString("api_url", normalized).apply()
        rebuildApiClient()
        session = null
        isAuthenticated = false
        screen = if (demoMode) GuardianScreen.SETUP else GuardianScreen.LOGIN
        checkConnection()
    }

    fun setDemoMode(enabled: Boolean) {
        if (demoMode == enabled) return
        demoMode = enabled
        preferences.edit().putBoolean("demo_mode", enabled).apply()
        session = null
        pairingChallenge = null
        device = null
        deviceId = if (enabled) DEMO_DEVICE_ID else ""
        preferences.edit().putString("device_id", deviceId).apply()
        rebuildApiClient()
        isAuthenticated = false
        screen = GuardianScreen.SETUP
        checkConnection()
    }

    fun saveChildId(value: String) {
        val normalized = value.trim()
        if (normalized.isBlank()) {
            error = "O ID da criança não pode ficar vazio."
            return
        }
        childId = normalized
        preferences.edit().putString("child_id", normalized).apply()
        pairingChallenge = null
        notice = "Perfil protegido atualizado"
        if (demoMode || isAuthenticated) refreshDashboard()
    }

    fun createPairingChallenge() = load(successMessage = "Código de pareamento criado") {
        val challenge = api.createPairingChallenge(childId)
        onMain { pairingChallenge = challenge }
    }

    fun useDemoDevice() {
        if (!demoMode) return
        deviceId = DEMO_DEVICE_ID
        preferences.edit().putString("device_id", deviceId).apply()
        refreshDashboard()
    }

    fun checkConnection() = load(successMessage = "Guardian API acessível") {
        api.health()
        val nextCapabilities = api.capabilities()
        val nextSession = when {
            demoMode -> api.session()
            api.hasSession() -> api.session()
            else -> null
        }
        onMain {
            capabilities = nextCapabilities
            session = nextSession
            isAuthenticated = demoMode || nextSession != null
        }
    }

    fun clearMessages() {
        error = null
        notice = null
    }

    fun close() {
        executor.shutdownNow()
    }

    private fun rebuildApiClient() {
        api = GuardianApi(apiUrl, demoMode)
    }

    private fun fetchDashboardSnapshot(): DashboardSnapshot {
        val nextIncidents = api.incidents(childId)
        val nextReport = api.dailyReport(childId)
        val nextCapabilities = api.capabilities()
        val candidateDeviceId = when {
            demoMode -> DEMO_DEVICE_ID
            deviceId.isNotBlank() -> deviceId
            else -> nextIncidents.firstOrNull()?.deviceId.orEmpty()
        }
        val nextDevice = candidateDeviceId
            .takeIf(String::isNotBlank)
            ?.let { runCatching { api.device(it) }.getOrNull() }
        return DashboardSnapshot(
            incidents = nextIncidents,
            report = nextReport,
            capabilities = nextCapabilities,
            device = nextDevice,
            resolvedDeviceId = candidateDeviceId,
        )
    }

    private fun applyDashboardSnapshot(snapshot: DashboardSnapshot) {
        incidents = snapshot.incidents
        report = snapshot.report
        capabilities = snapshot.capabilities
        device = snapshot.device
        if (snapshot.resolvedDeviceId.isNotBlank() && snapshot.resolvedDeviceId != deviceId) {
            deviceId = snapshot.resolvedDeviceId
            preferences.edit().putString("device_id", deviceId).apply()
        }
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
                    error = throwable.message ?: "O Guardian não conseguiu concluir a operação."
                    if (throwable is GuardianApiException && throwable.statusCode == 401 && !demoMode) {
                        api.clearSession()
                        session = null
                        isAuthenticated = false
                        screen = GuardianScreen.LOGIN
                    }
                }
            }
        }
    }

    private fun onMain(block: () -> Unit) {
        activity.runOnUiThread(block)
    }

    private data class DashboardSnapshot(
        val incidents: List<Incident>,
        val report: DailyReport,
        val capabilities: ProductCapabilities,
        val device: Device?,
        val resolvedDeviceId: String,
    )

    companion object {
        // Local demo uses `adb reverse tcp:8000 tcp:8000`, preserving the API's loopback-only demo boundary.
        const val DEFAULT_API_URL = "http://127.0.0.1:8000"
        const val DEMO_DEVICE_ID = "device-demo"
    }
}
