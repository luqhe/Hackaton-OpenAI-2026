# ADR-0002 — Monólito modular FastAPI

- Status: Accepted
- Date: 2026-08-19
- Owners: Backend Engineering

## Context

O produto ainda está validando fluxo, dados e segurança. Microserviços adicionariam deploy, rede, consistência e operação antes de existir escala que os justifique.

## Decision

Manter um monólito modular FastAPI no piloto, separando domínio, persistência, integrações, tarefas e rotas por fronteiras internas. Operações assíncronas podem usar uma fila gerenciada somente quando houver caso concreto.

## Consequences

- Deploy e debugging simples.
- Transações e autorização centralizadas.
- Módulos precisam evitar dependências circulares e acesso direto indiscriminado ao banco.
- Extração de serviço só ocorre após perfil de escala, segurança ou ownership justificar.

