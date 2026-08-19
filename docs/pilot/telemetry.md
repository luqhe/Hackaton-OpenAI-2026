# Instrumentação técnica do alpha

> Roadmap: R5-05  
> Owner: Pilot Analytics / SRE  
> Status: instrumentação interna implementada; integração de dashboard externo pendente

## Eventos e minimização

`POST /api/pilot/onboarding-events` registra somente IDs pseudonimizados, sessão, estágio,
timestamps e idempotency key. O schema rejeita campos extras; texto visível, OCR, screenshot,
transcrição, explicação e evidência não pertencem à telemetria.

Estágios canônicos:

```text
STARTED → PRIVACY_REVIEWED → CONSENT_RECORDED → CHILD_PROFILE_CONFIGURED
→ DEVICE_PAIRED → PERMISSIONS_GRANTED → FIRST_HEALTHY_HEARTBEAT → SHADOW_READY
```

Um evento registra progresso; não comprova consentimento válido, aprovação jurídica ou proteção
ativa. O funil deve ser segmentado somente por coorte/versão autorizadas, sem inferir produtividade,
comportamento da criança ou qualidade parental.

Cada sessão começa em `STARTED`, percorre exatamente a ordem canônica e usa timestamps estritamente
crescentes. A partir de `DEVICE_PAIRED`, o dispositivo é obrigatório e não pode mudar. Retry deve
reutilizar a mesma idempotency key e o mesmo payload, incluindo `occurred_at`; pular etapas ou
reutilizar a chave com dados diferentes é rejeitado.

## Saúde do agente

Cada heartbeat persiste uma amostra técnica com versão, permissões, saúde do observer, fila,
estado, horário observado e recebido. `GET /api/pilot/metrics?since_hours=24` retorna contagem de
amostras, percentual `PROTECTED`, maior idade do heartbeat mais recente por dispositivo e fila
máxima. Ausência de amostra resulta em `null`, nunca em saúde de 100%.

`observed_at` exige timezone e aceita no máximo 30 segundos de clock skew futuro; valores além disso
são rejeitados em vez de virarem idade zero. Heartbeat recebido com mais de 90 segundos já entra
como `DEGRADED`, mesmo que permissões e observer sejam declarados saudáveis.

## Latência de comando

A latência E2E usa timestamps persistidos:

```text
device_commands.created_at → device_commands.acknowledged_at
```

O relatório expõe contagem, p50, p95 e máximo em milissegundos. Comando pendente não entra no
percentil e precisa de métrica/alerta separado; latência negativa é rejeitada para zero no relatório
e deve ser investigada como clock/data inconsistente. O SLO inicial é p95 ≤ 5 segundos.

## Operação e retenção

- consultar janelas de 1 a 168 horas;
- agregar no dashboard do piloto sem dimensões de conteúdo;
- alertar falta de ingestão, heartbeat > 90 s e p95 > 5 s;
- limitar acesso ao time operacional mínimo;
- aplicar TTL aprovado e excluir junto à família;
- versionar mudança de estágio, campo ou definição de latência.

Esta implementação fornece armazenamento e relatório local. Ativar coleta de famílias exige os
gates de identidade, tenant, aprovação, retenção e observabilidade externa do protocolo.
