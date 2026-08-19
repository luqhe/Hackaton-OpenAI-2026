# ADR-0001 — Helper nativo Swift com agente Python

- Status: Accepted
- Date: 2026-08-19
- Owners: macOS Engineering

## Context

ScreenCaptureKit, Vision, permissões e ciclo de vida do macOS são melhor atendidos por APIs nativas. O MVP já possui contratos, policy engine, API client e fixtures em Python.

## Decision

Usar um helper Swift pequeno e assinado para captura, metadados de janela, OCR e sinais de permissão. Manter orquestração, contexto, risk engine e comunicação no agente Python durante o piloto técnico. O contrato helper → agente será versionado, estruturado e sem comandos arbitrários.

## Consequences

- Melhor integração e diagnóstico de permissões macOS.
- Reutilização do núcleo Python existente.
- Dois runtimes aumentam empacotamento e observabilidade.
- O helper deve validar tamanho, tipo e destino de arquivos.
- Uma futura migração completa para Swift exige novo ADR e medição objetiva.

