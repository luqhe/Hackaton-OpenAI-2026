# Referência rápida do suporte

> Roadmap: R5-03 · usar junto ao protocolo e playbooks

## Primeiro minuto

1. Há risco de dados, acesso cruzado, coleta proibida ou bloqueio inesperado?
2. Identifique severidade e acione on-call; qualquer pessoa pode interromper um `SEV0`.
3. Colete somente IDs técnicos, horário, versão, estado/permissões e correlation ID.
4. Não peça conteúdo, screenshot, credencial ou explicação da criança.

## Rotas de diagnóstico

| Sintoma | Verificar | Ação segura |
|---|---|---|
| agente offline/degradado | heartbeat, permissões, versão, fila | manter fail-open e escalar se persistente |
| classificação incorreta | categoria, versão, modo, decisão humana | triagem Evals/Product Safety, sem mudar gate |
| unlock lento | decisão, command ID, polling e ack | prioridade máxima; `SEV1` se janela/SLO excedido |
| evidência indisponível | autorização, objeto e TTL | não solicitar cópia por ticket |
| acesso cruzado/coleta proibida | escopo técnico mínimo | `SEV0`, parar coleta e revogar acesso |
| retirada/exclusão | identidade e escopo da família | cessar coleta e acionar processo verificável |

## Encerramento do ticket

- registrar estado final e timestamps, sem conteúdo observado;
- confirmar comunicação factual à família;
- vincular incidente/postmortem quando aplicável;
- abrir regressão para falha reproduzível;
- nunca marcar resolvido apenas porque o alerta parou.
