package com.guardian.mobile

import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL

class GuardianApi(baseUrl: String) {
    private val baseUrl = baseUrl.trim().trimEnd('/')

    fun health(): JSONObject = JSONObject(request("GET", "/api/health"))

    fun capabilities(): ProductCapabilities {
        val json = JSONObject(request("GET", "/api/capabilities"))
        return ProductCapabilities(
            environment = json.optString("environment"),
            apiVersion = json.optString("api_version"),
            fixtureAnalysis = json.optBoolean("fixture_analysis"),
            realScreenObservation = json.optBoolean("real_screen_observation"),
            simulatedEnforcement = json.optBoolean("simulated_enforcement"),
            productionReady = json.optBoolean("production_ready"),
            notes = json.optJSONArray("notes").strings(),
        )
    }

    fun device(deviceId: String): Device {
        val json = JSONObject(request("GET", "/api/devices/${encode(deviceId)}"))
        return json.toDevice()
    }

    fun pairDevice(childId: String, deviceName: String): Device {
        val body = JSONObject()
            .put("child_id", childId)
            .put("device_name", deviceName)
            .put("platform", "Android")
        return JSONObject(request("POST", "/api/devices/pair", body.toString())).toDevice()
    }

    fun incidents(childId: String = "child-demo"): List<Incident> {
        val json = JSONArray(request("GET", "/api/incidents?child_id=${encode(childId)}&limit=50"))
        return (0 until json.length()).map { json.getJSONObject(it).toIncident() }
    }

    fun incident(incidentId: String): Incident =
        JSONObject(request("GET", "/api/incidents/${encode(incidentId)}")).toIncident()

    fun dailyReport(childId: String = "child-demo"): DailyReport {
        val json = JSONObject(request("GET", "/api/daily-report?child_id=${encode(childId)}"))
        return DailyReport(
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

    fun policy(childId: String = "child-demo"): List<PolicyRule> {
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

    fun replacePolicy(rules: List<PolicyRule>, childId: String = "child-demo"): List<PolicyRule> {
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
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val response = stream?.bufferedReader()?.use(BufferedReader::readText).orEmpty()
            if (status !in 200..299) {
                val detail = runCatching { JSONObject(response).optString("detail") }.getOrNull()
                throw GuardianApiException(detail?.takeIf(String::isNotBlank) ?: "HTTP $status from Guardian API")
            }
            return response
        } finally {
            connection.disconnect()
        }
    }

    private fun encode(value: String): String = java.net.URLEncoder.encode(value, Charsets.UTF_8.name())
}

class GuardianApiException(message: String) : RuntimeException(message)

private fun JSONObject.toDevice() = Device(
    id = optString("id"),
    name = optString("name"),
    platform = optString("platform"),
    protectionStatus = optString("protection_status"),
)

private fun JSONObject.toIncident() = Incident(
    id = optString("id"),
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
