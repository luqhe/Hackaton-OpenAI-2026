package com.guardian.mobile

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

@Composable
fun GuardianMobileTheme(content: @Composable () -> Unit) {
    MaterialTheme(content = content)
}

@Composable
fun GuardianMobileApp(controller: GuardianController) {
    Scaffold(
        topBar = {
            Surface(shadowElevation = 2.dp) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("GUARDIAN", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        Text(screenTitle(controller.screen), style = MaterialTheme.typography.titleLarge)
                    }
                    TextButton(onClick = { controller.open(GuardianScreen.SETUP) }) {
                        Text("Conexão")
                    }
                }
            }
        },
        bottomBar = {
            if (controller.screen != GuardianScreen.INCIDENT && controller.screen != GuardianScreen.SETUP) {
                NavigationBar {
                    NavItem("Início", controller.screen == GuardianScreen.DASHBOARD) {
                        controller.open(GuardianScreen.DASHBOARD)
                    }
                    NavItem("Lucas", controller.screen == GuardianScreen.CHILD) {
                        controller.open(GuardianScreen.CHILD)
                    }
                    NavItem("Políticas", controller.screen == GuardianScreen.POLICIES) {
                        controller.open(GuardianScreen.POLICIES)
                    }
                }
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            if (controller.loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            controller.error?.let { MessageCard(it, true, controller::clearMessages) }
            controller.notice?.let { MessageCard(it, false, controller::clearMessages) }

            when (controller.screen) {
                GuardianScreen.DASHBOARD -> DashboardScreen(controller)
                GuardianScreen.INCIDENT -> IncidentScreen(controller)
                GuardianScreen.CHILD -> ChildScreen(controller)
                GuardianScreen.POLICIES -> PoliciesScreen(controller)
                GuardianScreen.SETUP -> SetupScreen(controller)
            }
        }
    }
}

@Composable
private fun NavItem(label: String, selected: Boolean, onClick: () -> Unit) {
    NavigationBarItem(
        selected = selected,
        onClick = onClick,
        icon = { Text(if (selected) "●" else "○") },
        label = { Text(label) },
    )
}

@Composable
private fun DashboardScreen(controller: GuardianController) {
    val report = controller.report
    val capabilities = controller.capabilities
    val device = controller.device

    SectionCard {
        Text("Perfil protegido", style = MaterialTheme.typography.labelMedium)
        Text(report?.childName ?: "Lucas", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(
            device?.let { "${it.name} · ${it.platform}" } ?: "Dispositivo demo · ${controller.deviceId}",
            style = MaterialTheme.typography.bodyMedium,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            if (capabilities?.realScreenObservation == true) "Proteção ativa" else "Demonstração segura",
            fontWeight = FontWeight.SemiBold,
        )
        if (capabilities?.simulatedEnforcement == true) {
            Text("Bloqueios são simulados nesta configuração.", style = MaterialTheme.typography.bodySmall)
        }
    }

    Text("Hoje", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        MetricCard("Tempo de tela", formatDuration(report?.totalSeconds ?: 0), Modifier.weight(1f))
        MetricCard("Incidentes", (report?.incidentCount ?: 0).toString(), Modifier.weight(1f))
    }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        MetricCard("Intervenções", (report?.interventions ?: 0).toString(), Modifier.weight(1f))
        MetricCard("Observações", (report?.screenChanges ?: 0).toString(), Modifier.weight(1f))
    }

    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("Atividade de proteção", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
        TextButton(onClick = controller::refreshDashboard) { Text("Atualizar") }
    }

    if (controller.incidents.isEmpty()) {
        SectionCard {
            Text("✓ Nenhum incidente", fontWeight = FontWeight.Bold)
            Text("Execute uma fixture controlada no backend para demonstrar o fluxo completo.")
        }
    } else {
        controller.incidents.take(10).forEach { incident ->
            IncidentRow(incident) { controller.openIncident(incident.id) }
        }
    }

    SectionCard {
        Text("Como o Guardian decide", fontWeight = FontWeight.Bold)
        Text("Contexto → avaliação de risco → política familiar determinística → ação.")
        Text(
            "O app Android não toma decisões de segurança por conta própria; ele consome o mesmo backend e as mesmas regras do projeto original.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun IncidentRow(incident: Incident, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(18.dp),
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("!", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(categoryLabel(incident.category), fontWeight = FontWeight.SemiBold)
                Text(incident.application, style = MaterialTheme.typography.bodySmall)
            }
            Text(statusLabel(incident.status), style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun IncidentScreen(controller: GuardianController) {
    val incident = controller.selectedIncident
    TextButton(onClick = { controller.open(GuardianScreen.DASHBOARD) }) { Text("← Voltar") }
    if (incident == null) {
        Text("Nenhum incidente selecionado.")
        return
    }

    SectionCard {
        Text("INCIDENTE", style = MaterialTheme.typography.labelSmall)
        Text(categoryLabel(incident.category), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(statusLabel(incident.status), fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        Text(incident.explanation)
    }

    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        MetricCard("Aplicativo", incident.application, Modifier.weight(1f))
        MetricCard("Confiança", "${(incident.confidence * 100).toInt()}%", Modifier.weight(1f))
    }

    SectionCard {
        Text("Sinais relevantes", fontWeight = FontWeight.Bold)
        if (incident.evidence.isEmpty()) Text("Sem evidência textual selecionada.")
        incident.evidence.forEach { Text("• $it") }
        if (incident.screenshotUrls.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text("${incident.screenshotUrls.size} evidência(s) visual(is) disponível(is) no servidor.", style = MaterialTheme.typography.bodySmall)
        }
    }

    SectionCard {
        Text("Decisão da família", fontWeight = FontWeight.Bold)
        incident.childExplanation?.let {
            Text("Explicação de Lucas", style = MaterialTheme.typography.labelMedium)
            Text(it)
        } ?: Text("Lucas ainda não enviou uma explicação.")
        Spacer(Modifier.height(10.dp))
        val canDecide = incident.status == "BLOCKED" || incident.status == "UNLOCK_REQUESTED"
        Button(
            onClick = controller::unlockSelected,
            enabled = canDecide && !controller.loading,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Desbloquear aplicativo") }
        OutlinedButton(
            onClick = controller::keepSelectedBlocked,
            enabled = canDecide && !controller.loading,
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Manter bloqueado") }
    }
}

@Composable
private fun ChildScreen(controller: GuardianController) {
    val report = controller.report
    Text("Seu dia digital", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        MetricCard("Uso", formatDuration(report?.totalSeconds ?: 0), Modifier.weight(1f))
        MetricCard("Incidentes", (report?.incidentCount ?: 0).toString(), Modifier.weight(1f))
    }

    SectionCard {
        Text("Aplicativos hoje", fontWeight = FontWeight.Bold)
        if (report?.apps.isNullOrEmpty()) {
            Text("Nenhuma sessão agregada ainda.")
        } else {
            report?.apps?.forEach { usage ->
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(usage.app, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(formatDuration(usage.seconds), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }

    SectionCard {
        Text("Transparência", fontWeight = FontWeight.Bold)
        Text("✓ Incidentes de segurança")
        Text("✓ Uso diário agregado por aplicativo")
        Text("✓ Evidência mínima associada a incidente")
        Text("— Tela ao vivo não é coletada")
        Text("— Microfone não é coletado")
        Text("— Câmera não é coletada")
    }

    val pending = controller.incidents.firstOrNull { it.status == "BLOCKED" || it.status == "UNLOCK_REQUESTED" }
    if (pending != null) {
        OutlinedButton(onClick = { controller.openIncident(pending.id) }, modifier = Modifier.fillMaxWidth()) {
            Text("Revisar bloqueio atual")
        }
    }
}

@Composable
private fun PoliciesScreen(controller: GuardianController) {
    Text("Políticas de proteção", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    Text("A classificação identifica contexto; estas regras determinísticas escolhem a ação.")

    controller.policies.forEach { rule ->
        PolicyRow(rule, enabled = !controller.loading) { action ->
            controller.updatePolicy(rule.category, action)
        }
    }

    Button(
        onClick = controller::savePolicies,
        enabled = controller.policies.isNotEmpty() && !controller.loading,
        modifier = Modifier.fillMaxWidth(),
    ) { Text("Salvar políticas") }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PolicyRow(rule: PolicyRule, enabled: Boolean, onAction: (String) -> Unit) {
    var expanded by remember(rule.category) { mutableStateOf(false) }
    SectionCard {
        Text(categoryLabel(rule.category), fontWeight = FontWeight.SemiBold)
        Text("Risco mínimo: ${rule.minimumRisk} · confiança ${(rule.minimumConfidence * 100).toInt()}%", style = MaterialTheme.typography.bodySmall)
        Box {
            OutlinedButton(onClick = { expanded = true }, enabled = enabled) {
                Text(policyLabel(rule.action))
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                listOf("ALLOW", "ALERT", "BLOCK").forEach { action ->
                    DropdownMenuItem(
                        text = { Text(policyLabel(action)) },
                        onClick = {
                            expanded = false
                            onAction(action)
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun SetupScreen(controller: GuardianController) {
    var url by remember(controller.apiUrl) { mutableStateOf(controller.apiUrl) }
    TextButton(onClick = { controller.open(GuardianScreen.DASHBOARD) }) { Text("← Voltar") }
    Text("Conexão com o Guardian", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

    SectionCard {
        OutlinedTextField(
            value = url,
            onValueChange = { url = it },
            label = { Text("URL da API") },
            supportingText = { Text("Emulador: http://10.0.2.2:8000") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(onClick = { controller.saveApiUrl(url) }, modifier = Modifier.fillMaxWidth()) {
            Text("Salvar e testar conexão")
        }
    }

    SectionCard {
        Text("Dispositivo", fontWeight = FontWeight.Bold)
        Text("ID atual: ${controller.deviceId}", style = MaterialTheme.typography.bodySmall)
        controller.device?.let { Text("${it.name} · ${it.platform}") }
        Button(onClick = controller::pairThisDevice, enabled = !controller.loading, modifier = Modifier.fillMaxWidth()) {
            Text("Parear este Android")
        }
        OutlinedButton(onClick = controller::useDemoDevice, enabled = !controller.loading, modifier = Modifier.fillMaxWidth()) {
            Text("Usar dispositivo demo")
        }
    }

    SectionCard {
        Text("Capacidades do servidor", fontWeight = FontWeight.Bold)
        val capabilities = controller.capabilities
        if (capabilities == null) {
            Text("Teste a conexão para carregar as capacidades.")
        } else {
            Text("Ambiente: ${capabilities.environment}")
            Text("API: ${capabilities.apiVersion}")
            Text("Fixtures: ${yesNo(capabilities.fixtureAnalysis)}")
            Text("Observação real: ${yesNo(capabilities.realScreenObservation)}")
            Text("Enforcement simulado: ${yesNo(capabilities.simulatedEnforcement)}")
            Text("Pronto para produção: ${yesNo(capabilities.productionReady)}")
        }
    }

    SectionCard {
        Text("Permissões Android", fontWeight = FontWeight.Bold)
        Text("Esta versão solicita somente acesso à internet.")
        Text("Captura de tela, Accessibility, microfone, câmera e administração do dispositivo não são habilitados por padrão.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun MetricCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, shape = RoundedCornerShape(18.dp)) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(label, style = MaterialTheme.typography.labelMedium)
            Text(value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, maxLines = 2)
        }
    }
}

@Composable
private fun SectionCard(content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            content()
        }
    }
}

@Composable
private fun MessageCard(message: String, isError: Boolean, onDismiss: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (isError) "Erro: $message" else message, modifier = Modifier.weight(1f))
            TextButton(onClick = onDismiss) { Text("Fechar") }
        }
    }
}

private fun screenTitle(screen: GuardianScreen) = when (screen) {
    GuardianScreen.DASHBOARD -> "Visão geral"
    GuardianScreen.INCIDENT -> "Revisar incidente"
    GuardianScreen.CHILD -> "Lucas"
    GuardianScreen.POLICIES -> "Políticas"
    GuardianScreen.SETUP -> "Configuração"
}

private fun categoryLabel(category: String) = when (category) {
    "DANGEROUS_CONTACT" -> "Contato potencialmente perigoso"
    "ADULT_CONTENT" -> "Conteúdo adulto"
    "HATE_SPEECH" -> "Discurso de ódio"
    else -> "Outro sinal"
}

private fun statusLabel(status: String) = when (status) {
    "BLOCKED" -> "Bloqueado"
    "DETECTED" -> "Detectado"
    "UNLOCK_REQUESTED" -> "Revisão solicitada"
    "UNLOCKED" -> "Desbloqueado"
    "KEPT_BLOCKED" -> "Bloqueio mantido"
    else -> status
}

private fun policyLabel(action: String) = when (action) {
    "ALLOW" -> "Permitir"
    "ALERT" -> "Somente alertar"
    "BLOCK" -> "Bloquear"
    else -> action
}

private fun formatDuration(seconds: Int): String {
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    return if (hours > 0) "${hours}h ${minutes}min" else "${minutes}min"
}

private fun yesNo(value: Boolean) = if (value) "sim" else "não"
