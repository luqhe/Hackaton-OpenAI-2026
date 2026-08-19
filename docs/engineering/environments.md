# Ambientes do Guardian

> Status: aceito  
> Roadmap: R0-17

## Ambientes

| Ambiente | Finalidade | Dados permitidos | Bloqueio automático | Enforcement real |
|---|---|---|---|---|
| `development` | desenvolvimento e demo local | fixtures e dados sintéticos | somente fixtures | opt-in/allowlist local |
| `test` | testes automatizados | dados gerados pelo teste | desabilitado | proibido |
| `staging` | integração e shadow mode | dados sintéticos ou coorte formalmente autorizada | desabilitado por padrão | exige release gate |
| `production` | famílias liberadas | dados reais minimizados | exige gate por categoria | exige gate e agente assinado |

Os exemplos ficam em `config/environments/*.env.example`. Segredos nunca são commitados; os arquivos documentam somente chaves e valores seguros de exemplo.

## Regras de configuração

- `GUARDIAN_ENVIRONMENT` é obrigatório fora de desenvolvimento.
- `GUARDIAN_AUTOMATIC_BLOCKING_ENABLED=true` em staging/produção exige `GUARDIAN_RELEASE_GATE_APPROVED=true`.
- `GUARDIAN_REAL_ENFORCEMENT_ENABLED=true` em staging/produção exige o mesmo gate.
- Produção continua com `production_ready=false` até autenticação, tenancy e storage gerenciado existirem.
- Caminhos de SQLite dos exemplos não representam arquitetura final de staging/produção.
- Toda alteração de configuração sensível precisa aparecer em auditoria quando essa capacidade existir.

## Promoção

```text
feature branch
  ↓ CI
development
  ↓ revisão + testes de integração
staging
  ↓ release gate + change record
production gradual
```

Não é permitido promover banco, evidência ou arquivos `.env` entre ambientes. Somente código versionado, migrations e configurações aprovadas são promovidos.

## Flags críticas

| Flag | Default seguro | Observação |
|---|---|---|
| `GUARDIAN_AUTOMATIC_BLOCKING_ENABLED` | `false` fora da demo | não substitui gate por categoria |
| `GUARDIAN_REAL_ENFORCEMENT_ENABLED` | `false` | requer agente compatível e allowlist |
| `GUARDIAN_RELEASE_GATE_APPROVED` | `false` | aprovação precisa ser rastreável fora de env var no futuro |
| `GUARDIAN_LOG_LEVEL` | `INFO`/`WARNING` | nunca habilita conteúdo bruto em log |

