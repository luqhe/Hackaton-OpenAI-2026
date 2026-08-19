# Contribuindo com o Guardian

## Fluxo

1. Relacione a mudança a um item do `ROADMAP.md` ou descreva o motivo.
2. Registre impacto em segurança, privacidade, retenção e enforcement.
3. Escreva teste antes ou junto da implementação.
4. Rode os checks locais.
5. Atualize contratos e documentação afetados.
6. Solicite revisão do owner técnico e, quando aplicável, Product Safety/Privacy.

## Checks locais

```bash
python -m pytest
python scripts/validate_stage0.py
python -m ruff check .
python -m ruff format --check agent api guardian_core risk_engine scripts tests
npm run lint:js
```

## Regras de mudança sensível

Exigem revisão adicional:

- nova fonte de dados ou aumento de retenção;
- mudança em limiar, taxonomia ou ação de política;
- alteração no enforcer, allowlist ou denylist;
- novo provider externo;
- mudança em autenticação, tenant ou evidência;
- desativação de teste/gate de segurança.

## Pull request

O PR deve informar:

- problema e solução;
- testes executados;
- riscos e rollback;
- alterações de dados/retention;
- evidência de UI quando houver mudança visual;
- tarefas do roadmap concluídas ou criadas.
