# ADR-0003 — PostgreSQL para dados e object storage para evidências

- Status: Accepted
- Date: 2026-08-19
- Owners: Backend Engineering, Privacy Engineering

## Context

SQLite e filesystem atendem à demo local, mas não oferecem tenancy, concorrência, gestão de backup e controle de blobs adequados ao piloto.

## Decision

Usar PostgreSQL gerenciado para dados estruturados e object storage privado para evidências. O banco mantém metadados, tenant, hash, retenção e chave do objeto; nunca caminhos arbitrários. Acesso a evidências usa autorização e URL temporária curta.

## Consequences

- Isolamento e migrations ficam verificáveis.
- Evidências podem expirar independentemente de metadados.
- Backups, região, chaves e subprocessadores precisam de revisão.
- SQLite continua suportado exclusivamente para desenvolvimento/teste local.

