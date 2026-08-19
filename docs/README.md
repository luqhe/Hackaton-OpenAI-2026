# Documentação do Guardian

Este diretório contém os artefatos normativos usados para implementar e liberar o Guardian.

## Produto

- [Gates de risco e lançamento](product/release-gates.md)

## Segurança e privacidade

- [Threat model](security/threat-model.md)
- [Mapa de dados e retenção](privacy/data-map.md)
- [Registro inicial de riscos](security/risk-register.md)
- [Playbooks de resposta](security/response-playbooks.md)

## Engenharia

- [Ambientes](engineering/environments.md)
- [Versionamento de API e migrations](engineering/api-versioning-and-migrations.md)
- [Architecture Decision Records](adr/README.md)

## Regra de precedência

Em caso de conflito, contratos executáveis e gates de segurança prevalecem sobre exemplos narrativos. Uma mudança em coleta, retenção, classificação ou enforcement precisa atualizar o artefato correspondente e seus testes.
