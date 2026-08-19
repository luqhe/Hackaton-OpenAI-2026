# Registro inicial de riscos

> Owner: Security & Product Safety  
> Status: aberto  
> Roadmap: R0-12

Escala: probabilidade e impacto de 1 (baixo) a 5 (crítico). Prioridade = probabilidade × impacto.

| ID | Risco | Prob. | Impacto | Prioridade | Owner | Mitigação principal | Gate | Estado |
|---|---|---:|---:|---:|---|---|---|---|
| RISK-001 | Falso positivo bloqueia app legítimo | 4 | 5 | 20 | Product Safety | evals, shadow mode, limiar alto, contestação e kill switch | antes de BLOCK | aberto |
| RISK-002 | Evidência de menor é exposta | 3 | 5 | 15 | Security | tenant, storage privado, URL curta, TTL e auditoria | antes do piloto | aberto |
| RISK-003 | App essencial é encerrado | 2 | 5 | 10 | macOS Engineering | denylist, allowlist assinada e E2E | antes do agente real | mitigação parcial |
| RISK-004 | Conta parental comprometida controla dispositivo | 3 | 5 | 15 | Identity | autenticação, revogação, alertas e auditoria | antes do piloto | aberto |
| RISK-005 | Agente removido sem informação à família | 4 | 3 | 12 | macOS Engineering | heartbeat, status degradado e recuperação | antes do piloto | aberto |
| RISK-006 | Prompt injection altera classificação | 4 | 4 | 16 | ML Safety | isolamento, schema, eval adversarial e fallback | antes de modelo remoto | aberto |
| RISK-007 | Retenção excede prazo definido | 3 | 5 | 15 | Privacy Engineering | TTL, auditoria de jobs e política de backup | antes do piloto | aberto |
| RISK-008 | Isolamento cross-tenant falha | 3 | 5 | 15 | Backend | autorização central e testes negativos | antes do piloto | aberto |
| RISK-009 | Desbloqueio demora ou se perde | 3 | 4 | 12 | Backend/Agent | prioridade de comando, retry, ack e SLO | antes do piloto | mitigação parcial |
| RISK-010 | Agente consome bateria excessiva | 4 | 3 | 12 | macOS Engineering | change detection, backoff e profiling | antes do piloto | aberto |
| RISK-011 | Provider remoto recebe dados desnecessários | 3 | 5 | 15 | Privacy/ML | pré-filtro local, minimização e contrato | antes de integração | aberto |
| RISK-012 | UI afirma proteção inexistente | 4 | 4 | 16 | Product/Frontend | capabilities reais e status por heartbeat | imediato | aberto |
| RISK-013 | Logs contêm texto/imagem sensíveis | 3 | 5 | 15 | Platform | logging estruturado, redaction e testes | antes do piloto | aberto |
| RISK-014 | Mudança de modelo degrada segurança | 4 | 4 | 16 | ML Safety | versionamento, regressão e approval gate | antes de modelo remoto | aberto |
| RISK-015 | Uso abusivo para vigilância ampla | 3 | 5 | 15 | Product/Privacy | sem live screen, transparência e acesso auditado | antes do piloto | aberto |

## Processo

- Revisar quinzenalmente durante as Etapas 1–4.
- Riscos com prioridade ≥ 15 exigem owner e plano antes do piloto.
- Risco crítico materializado aciona freeze de rollout e playbook correspondente.
- Fechar um risco exige evidência verificável, não apenas implementação declarada.

