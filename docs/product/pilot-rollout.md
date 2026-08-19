# Rollout do alpha supervisionado

> Owner: Product Safety + Pilot Operations  
> Estado inicial: `TECHNICAL_SHADOW`  
> Configuração ativa versionada: `config/pilot-rollout.v1.json`

## Fase 1 — telemetria técnica e shadow (R5-07)

O piloto começa em `TECHNICAL_SHADOW`. A política e o pipeline podem propor `ALERT` ou `BLOCK`,
mas o gate final converte a ação efetiva em `LOG`; a ação proposta existe somente no registro de
shadow e `actual_intervention=false`.

Somente os campos técnicos enumerados na configuração são aceitos: versão do agente, latências,
CPU, memória, bateria, profundidade da fila e estado de permissões. Texto visível, título de janela,
imagem, áudio, explicação, evidência e identificadores familiares não fazem parte dessa telemetria.

Uma coorte ausente da configuração também recebe no máximo `LOG`. Falha ao carregar ou validar a
configuração deve manter o último estado válido; sem estado válido, o comportamento é
`TECHNICAL_SHADOW` e nenhuma intervenção nova é permitida.

O arquivo versionado é deliberadamente conservador e não constitui autorização jurídica,
aprovação de Product Safety nem evidência de execução com famílias reais.
