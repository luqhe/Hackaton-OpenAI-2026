# ADR-0004 — Protocolo persistente e idempotente de comandos

- Status: Accepted
- Date: 2026-08-19
- Owners: Agent Engineering, Backend Engineering

## Context

Desbloqueios não podem ser perdidos, repetidos incorretamente ou executados por outro dispositivo. Push permanente acrescenta complexidade antes de existir escala medida.

## Decision

Persistir comandos por dispositivo, consultar por polling autenticado no piloto e confirmar execução por ack. Cada comando terá ID monotônico no escopo necessário, idempotency key, versão, criação, expiração e estado terminal. Long polling ou WebSocket só será adotado se a latência/SLO exigir.

## Consequences

- Funciona através de reconexão e reinício.
- Polling é simples e mensurável, mas gera tráfego periódico.
- Comando expirado ou desconhecido nunca é executado silenciosamente.
- Desbloqueio tem prioridade sobre telemetria e relatórios.

