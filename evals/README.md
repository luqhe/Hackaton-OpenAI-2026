# Guardian contextual-risk evals

- `dataset-manifest.v1.json`: origem, direitos e política de splits.
- `dataset-v1.jsonl`: casos sintéticos originais versionados.
- `regression-gate.v1.json`: limites congelados executados no CI.
- `results/eval-report.v1.json`: métricas reproduzíveis do classificador local no teste final.
- `results/shadow-summary.v1.json`: comparação da janela sintética sem intervenção.
- `results/shadow-windows.v1.json`: resultado por categoria e combinação de versões.
- `results/shadow-dashboard.v1.html`: dashboard interno estático de falsos positivos/negativos.

Execute `python scripts/run_r3_evals.py --check` para validar sem alterar artefatos ou `python scripts/run_r3_evals.py` para regenerar os relatórios versionados.

Os resultados medem somente este conjunto sintético pequeno. Eles não demonstram desempenho populacional, segurança pronta para produção nem autorização para monitorar menores reais.
