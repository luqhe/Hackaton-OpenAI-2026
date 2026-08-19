# Playbooks iniciais de resposta

> Status: baseline; contatos e obrigações devem ser preenchidos antes do piloto

## Playbook A — Evidência exposta

1. Suspender entrega de evidências e preservar logs técnicos necessários.
2. Revogar URLs, tokens e credenciais afetadas.
3. Identificar objetos, tenants, período e acessos envolvidos.
4. Isolar o componente sem ampliar cópias dos dados.
5. Acionar Security, Privacy e responsável jurídico designado.
6. Avaliar notificações e prazos aplicáveis com aconselhamento apropriado.
7. Corrigir a causa, criar teste de regressão e validar isolamento.
8. Reabrir gradualmente e publicar postmortem interno sem conteúdo sensível.

## Playbook B — Conta parental comprometida

1. Revogar sessões e pausar comandos novos.
2. Revogar links de evidência e revisar alterações de política.
3. Validar identidade por canal independente.
4. Rotacionar credenciais e reautorizar dispositivos.
5. Informar decisões tomadas durante a janela suspeita.
6. Restaurar acesso e acompanhar novos eventos de risco.

## Playbook C — Agente adulterado ou removido

1. Marcar o dispositivo como `DEGRADED`, nunca como protegido.
2. Informar a família de forma factual.
3. Revogar a credencial se houver sinal de cópia ou uso indevido.
4. Orientar reinstalação e concessão explícita de permissões.
5. Verificar integridade, versão e heartbeat antes de restaurar o status.

## Playbook D — Falso bloqueio em escala

1. Acionar kill switch da categoria/versão.
2. Priorizar entrega de comandos de desbloqueio.
3. Pausar rollout e preservar amostras mínimas autorizadas para diagnóstico.
4. Identificar versão, categoria, idioma e coorte afetados.
5. Reverter classificador/configuração.
6. Adicionar regressões ao conjunto de eval antes de reativar alertas.

