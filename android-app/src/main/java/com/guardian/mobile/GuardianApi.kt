package com.guardian.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

class GuardianApi(
    baseUrl: String,
    private val demoMode: Boolean = false,
) {
    private val baseUrl = baseUrl.trim().trimEnd('/')
    private var sessionCookie: String? = null
    private var csrfToken: String? = null

    fun hasSession(): Boolean = demoMode || sessionCookie != null

    fun clearSession() {
        sessionCookie = null
        csrfToken = null
    }

    fun health(): JSONObject = JSONObject(request("GET", "/api/health"))

    fun capabilities(): ProductCapabilities {
        val json = JSONObject(request("GET", "/api/capabilities"))
        return ProductCapabilities(
            environment = json.optString("environment"),
            apiVersion = json.optString("api_version"),
            fixtureAnalysis = json.optBoolean("fixture_analysis"),
            realScreenObservation = json.optBoolean("real_screen_observation"),
            simulatedEnforcement = json.optBoolean("simulated_enforcement"),
            authentication = json.optBoolean("authentication"),
            tenantIsolation = json.optBoolean("tenant_isolation"),
            productionReady = json.optBoolean("production_ready"),
            notes = json.optJSONArray("notes").strings(),
        )
    }

    fun login(email: String, password: String, familyId: String? = null): GuardianSession {
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
        familyId?.trim()?.takeIf(String::isNotBlank)?.let { body.put("family_id", it) }
        return JSONObject(request("POST", "/api/auth/login", body.toString())).toSession()
    }

    fun session(): GuardianSession =
        JSONObject(request("GET", "/api/auth/session")).toSession()

    fun logout() {
        if (!demoMode && sessionCookie != null) {
            request("POST", "/api/auth/logout")
        }
        clearSession()
    }

    fun device(deviceId: String): Device {
        val json = JSONObject(request("GET", "/api/devices/${encode(deviceId)}"))
        return json.toDevice()
    }

    fun createPairingChallenge(childId: String): PairingChallenge {
        val body = JSONObject().put("child_id", childId)
        val json = JSONObject(request("POST", "/api/pairing/challenges", body.toString()))
        return PairingChallenge(
            challengeId = json.optString("challenge_id"),
            code = json.optString("code"),
            expiresAt = json.optString("expires_at"),
        )
    }

    fun incidents(childId: String): List<Incident> {
        val json = JSONArray(request("GET", "/api/incidents?child_id=${encode(childId)}&limit=50"))
        return (0 until json.length()).map { json.getJSONObject(it).toIncident() }
    }

    fun incident(incidentId: String): Incident =
        JSONObject(request("GET", "/api/incidents/${encode(incidentId)}")).toIncident()

    fun dailyReport(childId: String): DailyReport {
        val json = JSONObject(request("GET", "/api/daily-report?child_id=${encode(childId)}"))
        return DailyReport(
            familyId = json.optString("family_id"),
            childId = json.optString("child_id"),
            childName = json.optString("child_name"),
            date = json.optString("date"),
            totalSeconds = json.optInt("total_seconds"),
            apps = json.optJSONArray("apps").objects().map { item ->
                DailyAppUsage(item.optString("app"), item.optInt("seconds"))
            },
            incidentCount = json.optInt("incident_count"),
            screenChanges = json.optInt("screen_changes"),
            interventions = json.optInt("interventions"),
            evidenceCount = json.optInt("evidence_count"),
        )
    }

    fun policy(childId: String): List<PolicyRule> {
        val json = JSONArray(request("GET", "/api/children/${encode(childId)}/policy"))
        return (0 until json.length()).map { index ->
            val item = json.getJSONObject(index)
            PolicyRule(
                category = item.optString("category"),
                action = item.optString("action"),
                minimumRisk = item.optString("minimum_risk"),
                minimumConfidence = item.optDouble("minimum_confidence"),
            )
        }
    }

    fun replacePolicy(rules: List<PolicyRule>, childId: String): List<PolicyRule> {
        val body = JSONArray()
        rules.forEach { rule ->
            body.put(
                JSONObject()
                    .put("category", rule.category)
                    .put("action", rule.action)
                    .put("minimum_risk", rule.minimumRisk)
                    .put("minimum_confidence", rule.minimumConfidence),
            )
        }
        val json = JSONArray(
            request("PUT", "/api/children/${encode(childId)}/policy", body.toString()),
        )
        return (0 until json.length()).map { index ->
            val item = json.getJSONObject(index)
            PolicyRule(
                category = item.optString("category"),
                action = item.optString("action"),
                minimumRisk = item.optString("minimum_risk"),
                minimumConfidence = item.optDouble("minimum_confidence"),
            )
        }
    }

    fun requestUnlock(incidentId: String, explanation: String): Incident {
        val body = JSONObject().put("explanation", explanation)
        return JSONObject(
            request("POST", "/api/incidents/${encode(incidentId)}/request-unlock", body.toString()),
        ).toIncident()
    }

    fun unlock(incidentId: String): Incident =
        JSONObject(request("POST", "/api/incidents/${encode(incidentId)}/unlock")).toIncident()

    fun keepBlocked(incidentId: String): Incident =
        JSONObject(request("POST", "/api/incidents/${encode(incidentId)}/keep-blocked")).toIncident()

    private fun request(method: String, path: String, body: String? = null): String {
        val connection = URL("$baseUrl$path").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 5_000
            connection.readTimeout = 10_000
            connection.setRequestProperty("Accept", "application/json")
            if (demoMode) {
                connection.setRequestProperty("X-Guardian-Demo", "true")
            }
            val cookies = buildList {
                sessionCookie?.let { add("guardian_session=$it") }
                csrfToken?.let { add("guardian_csrf=$it") }
            }
            if (cookies.isNotEmpty()) {
                connection.setRequestProperty("Cookie", cookies.joinToString("; "))
            }
            if (method in MUTATION_METHODS && csrfToken != null) {
                connection.setRequestProperty("X-CSRF-Token", csrfToken)
            }
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            }

            val status = connection.responseCode
            captureCookies(connection)
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
            if (status !in 200..299) {
                if (status == 401 && !demoMode) clearSession()
                val detail = runCatching { JSONObject(response).optString("detail") }.getOrNull()
                throw GuardianApiException(
                    status,
                    detail?.takeIf(String::isNotBlank) ?: "HTTP $status from Guardian API",
                )
            }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun captureCookies(connection: HttpURLConnection) {
        connection.headerFields.forEach { (name, values) ->
            if (name?.equals("Set-Cookie", ignoreCase = true) != true) return@forEach
            values.orEmpty().forEach { header ->
                val pair = header.substringBefore(';')
                val separator = pair.indexOf('=')
                if (separator <= 0) return@forEach
                val cookieName = pair.substring(0, separator).trim()
                val cookieValue = pair.substring(separator + 1).trim().takeIf(String::isNotEmpty)
                when (cookieName) {
                    "guardian_session" -> sessionCookie = cookieValue
                    "guardian_csrf" -> csrfToken = cookieValue
                }
            }
        }
    }

    private fun encode(value: String): String = java.net.URLEncoder.encode(value, Charsets.UTF_8.name())

    companion object {
        private val MUTATION_METHODS = setOf("POST", "PUT", "PATCH", "DELETE")
    }
}

class GuardianApiException(
    val statusCode: Int,
    message: String,
) : RuntimeException(message)

private fun JSONObject.toSession() = GuardianSession(
    accountId = optString("account_id"),
    familyId = optString("family_id"),
    membershipId = optString("membership_id"),
    role = optString("role"),
)

private fun JSONObject.toDevice() = Device(
    id = optString("id"),
    familyId = optString("family_id"),
    childId = optString("child_id"),
    name = optString("name"),
    platform = optString("platform"),
    lastSeenAt = if (isNull("last_seen_at")) null else optString("last_seen_at"),
    lifecycleStatus = optString("lifecycle_status"),
    protectionStatus = optString("protection_status"),
)

private fun JSONObject.toIncident() = Incident(
    id = optString("id"),
    familyId = optString("family_id"),
    childId = optString("child_id"),
    deviceId = optString("device_id"),
    application = optString("application"),
    occurredAt = optString("occurred_at"),
    category = optString("category"),
    direction = optString("direction"),
    severity = optString("severity"),
    confidence = optDouble("confidence"),
    explanation = optString("explanation"),
    evidence = optJSONArray("evidence").strings(),
    status = optString("status"),
    childExplanation = if (isNull("child_explanation")) null else optString("child_explanation"),
    screenshotUrls = optJSONArray("screenshot_urls").strings(),
)

private fun JSONArray?.strings(): List<String> {
    if (this == null) return emptyList()
    return (0 until length()).map { optString(it) }
}

private fun JSONArray?.objects(): List<JSONObject> {
    if (this == null) return emptyList()
    return (0 until length()).map { getJSONObject(it) }
}
