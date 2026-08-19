package com.guardian.mobile

data class GuardianSession(
    val accountId: String,
    val familyId: String,
    val membershipId: String,
    val role: String,
)

data class PairingChallenge(
    val challengeId: String,
    val code: String,
    val expiresAt: String,
)

data class Device(
    val id: String,
    val familyId: String,
    val childId: String,
    val name: String,
    val platform: String,
    val lastSeenAt: String?,
    val lifecycleStatus: String,
    val protectionStatus: String,
)

data class Incident(
    val id: String,
    val familyId: String,
    val childId: String,
    val deviceId: String,
    val application: String,
    val occurredAt: String,
    val category: String,
    val direction: String,
    val severity: String,
    val confidence: Double,
    val explanation: String,
    val evidence: List<String>,
    val status: String,
    val childExplanation: String?,
    val screenshotUrls: List<String>,
)

data class DailyAppUsage(
    val app: String,
    val seconds: Int,
)

data class DailyReport(
    val familyId: String,
    val childId: String,
    val childName: String,
    val date: String,
    val totalSeconds: Int,
    val apps: List<DailyAppUsage>,
    val incidentCount: Int,
    val screenChanges: Int,
    val interventions: Int,
    val evidenceCount: Int,
)

data class PolicyRule(
    val category: String,
    val action: String,
    val minimumRisk: String,
    val minimumConfidence: Double,
)

data class ProductCapabilities(
    val environment: String,
    val apiVersion: String,
    val fixtureAnalysis: Boolean,
    val realScreenObservation: Boolean,
    val simulatedEnforcement: Boolean,
    val authentication: Boolean,
    val tenantIsolation: Boolean,
    val productionReady: Boolean,
    val notes: List<String>,
)

enum class GuardianScreen {
    LOGIN,
    DASHBOARD,
    INCIDENT,
    CHILD,
    POLICIES,
    SETUP,
}
