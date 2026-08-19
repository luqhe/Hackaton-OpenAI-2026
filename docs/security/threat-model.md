# Threat model do Guardian

> Owner: Security Engineering  
> Status: baseline para revisão da equipe  
> Roadmap: R0-07 a R0-11

## 1. Escopo — R0-07

O modelo cobre:

- agente e helper nativo no Mac da criança;
- arquivos temporários e estado local;
- comunicação agente ↔ API;
- API, banco e armazenamento de evidências;
- dashboard do responsável e tela de transparência da criança;
- canal de comandos de bloqueio/desbloqueio;
- fornecedores de análise contextual, quando adicionados.

Checkout, cobrança e plataformas móveis estão fora do escopo atual.

## 2. Ativos

| Ativo | Sensibilidade | Consequência de comprometimento |
|---|---|---|
| Evidência de incidente | Crítica | exposição de conteúdo privado de menor e terceiros |
| Context buffer/OCR | Crítica e efêmera | reconstrução parcial da atividade digital |
| Credencial do dispositivo | Alta | falsificação de incidentes ou comandos |
| Conta do responsável | Alta | acesso indevido e decisões de enforcement |
| Política familiar | Alta | bloqueio indevido ou remoção silenciosa de proteção |
| Canal de desbloqueio | Alta | manutenção indevida de bloqueio ou liberação não autorizada |
| Telemetria agregada | Moderada | inferência de hábitos e rotina |
| Logs/auditoria | Alta | exposição indireta ou ocultação de abuso |

## 3. Fronteiras de confiança

```text
Conteúdo não confiável na tela
        ↓
Mac da criança [ambiente parcialmente hostil]
        ↓ canal autenticado e criptografado
Control Plane [tenant boundary]
        ↓ sessão autenticada
Dashboard do responsável
        ↓ integração mínima e contratada
Provider de análise [subprocessador futuro]
```

Texto visível, nomes de janela, transcrições e imagens são sempre dados não confiáveis, nunca instruções para o sistema.

## 4. Ameaças e controles

| ID | Ameaça | Vetor | Controle atual | Controle requerido antes do piloto |
|---|---|---|---|---|
| T-01 | Prompt injection visual | texto na tela tenta alterar a decisão | heurística não executa instruções | isolamento de prompt, schema e eval adversarial |
| T-02 | Exfiltração de evidência | URL pública, log ou ID previsível | caminho interno e no-store | object storage privado, URL curta e autorização por tenant |
| T-03 | Conta parental comprometida | senha/session theft | nenhum controle de conta no MVP | autenticação, revogação, alerta e auditoria |
| T-04 | Dispositivo falsificado | cliente chama API como outro Mac | IDs hardcoded no MVP | credencial única no Keychain e rotação |
| T-05 | Adulteração do agente | processo/configuração alterados | denylist e opt-in local | assinatura, integridade, heartbeat e estado degradado visível |
| T-06 | Remoção do agente | criança encerra ou desinstala | sem proteção persistente | launcher, detecção de ausência e aviso sem vigilância oculta |
| T-07 | Comando repetido/reordenado | retry ou replay de unlock | ack e status persistido | expiração, idempotency key e sequência por dispositivo |
| T-08 | Bloqueio de processo essencial | classificação/app incorretos | denylist local | allowlist assinada e teste E2E obrigatório |
| T-09 | Vazamento cross-tenant | autorização ausente/incorreta | aplicação single-family | tenant em toda query e teste negativo automatizado |
| T-10 | Retenção excessiva | falha no job ou backup | exclusão manual local | TTL, prova de exclusão e política para backups |
| T-11 | Logs sensíveis | screenshot/texto em exception | logs atuais limitados | redaction central e teste de conteúdo proibido |
| T-12 | Provider indisponível/comprometido | timeout ou output malicioso | fail-open conceitual | circuit breaker, validação e kill switch |
| T-13 | Responsável abusivo | uso para vigilância ampla | transparência conceitual | minimização, ausência de live screen e trilha de acesso |
| T-14 | Evidência forjada | payload arbitrário enviado à API | tipos/tamanho validados | dispositivo autenticado, hash, timestamp e proveniência |

## 5. Comprometimento da conta do responsável — R0-09

Ao detectar ou receber relato de comprometimento:

1. Revogar sessões da conta.
2. Suspender novos comandos de enforcement até reautenticação segura.
3. Não desbloquear automaticamente apps já bloqueados; oferecer caminho local de suporte com verificação.
4. Revogar links ativos de evidência.
5. Preservar somente auditoria necessária, sem duplicar conteúdo sensível.
6. Notificar contatos verificados por canal independente.
7. Exigir rotação de credenciais e revisar mudanças recentes de política.

O MVP não implementa esses controles; a Etapa 2 deve torná-los executáveis.

## 6. Adulteração ou remoção do agente — R0-10

- O status muda para `DEGRADED` quando heartbeat ou permissões expiram.
- O dashboard nunca exibe “Proteção ativa” baseado apenas em cadastro no banco.
- O responsável recebe informação factual sobre perda de proteção, sem acusar a criança.
- O sistema não coleta secretamente para contornar consentimento ou permissões do macOS.
- O agente se recupera após reinício, mas não tenta obter privilégios além dos explicitamente concedidos.

## 7. Vazamento de evidência e revogação — R0-11

1. Desativar imediatamente entrega de evidências e rotacionar credenciais afetadas.
2. Identificar famílias, objetos, logs e backups potencialmente envolvidos.
3. Acionar o playbook [Evidência exposta](response-playbooks.md#playbook-a--evidência-exposta).
4. Preservar a cadeia de investigação com acesso mínimo.
5. Executar exclusão/isolamento conforme impacto e obrigações aplicáveis.
6. Revalidar isolamento por tenant antes de reabrir o serviço.

## 8. Riscos aceitos apenas no MVP local

- ausência de autenticação e tenancy;
- SQLite e filesystem locais;
- enforcement simulado ou allowlist manual;
- evidência de fixture sem criptografia de aplicação;
- ausência de assinatura e atualização do agente.

Nenhum desses riscos é aceito para dados reais de famílias.

