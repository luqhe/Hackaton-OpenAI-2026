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

## Fase 2 — alertas aprovados, sem bloqueio (R5-08)

A promoção para `ALERT_ONLY` exige uma aprovação que identifique categoria, coorte, janela de shadow
representativa e versões exatas de modelo, prompt e dataset. Os gates de eval e shadow, Product
Safety e Engineering precisam estar todos aprovados. Mudança em qualquer versão invalida o gate.

Nessa fase, uma decisão `BLOCK` aprovada produz no máximo `ALERT`. Categoria sem aprovação, coorte
fora do escopo, versão divergente ou aprovação incompleta produz no máximo `LOG`. O baseline
versionado mantém `alert_approvals=[]`; preencher a lista demanda evidência externa real e revisão.

## Revisão controlada de eventos (R5-09)

O reviewer recebe um grant just-in-time associado a um ticket, com identidade pseudonimizada,
categorias e coortes explícitas e validade máxima de uma hora. O grant padrão permite apenas a
projeção mínima do evento: horário, categoria, confiança, ações proposta/efetiva e digest do
contexto. Não inclui texto observado, título de janela, identificador familiar ou conteúdo binário.

O acesso a uma referência de evidência exige solicitação explícita e `evidence_access=true`; ainda
assim, o contrato retorna somente o identificador do objeto, deixando autenticação e entrega para
o storage privado. Todo acesso autorizado gera uma entrada append-only com grant, ticket, campos
consultados e indicação de evidência divulgada. Acesso expirado ou fora de escopo falha fechado.

Processo operacional:

1. abrir ticket com finalidade e evento;
2. emitir grant mínimo e temporário por pessoa;
3. revisar primeiro apenas metadados;
4. elevar para evidência somente quando indispensável e documentado;
5. registrar o acesso no audit store e revogar/expirar o grant;
6. escalar suspeita de privacidade conforme o playbook de resposta.

Esse contrato não substitui a autenticação e o isolamento multi-tenant requeridos antes de operar
com famílias reais; ele define e testa a fronteira mínima que a futura API autenticada deve aplicar.

## Métricas de segurança e compreensão (R5-10)

O relatório de piloto calcula taxas com denominadores explícitos e sempre segmentadas por coorte:

- falso positivo = eventos marcados pelo modelo e revisados como seguros / eventos marcados e
  revisados por humano;
- contestação = incidentes contestados / incidentes exibidos à família;
- compreensão da intervenção = média da pergunta estruturada em escala 1–5;
- confiança no Guardian = média da pergunta estruturada em escala 1–5.

O survey guarda somente ID de resposta, digest pseudônimo da família, horário, coorte e duas notas;
não há campo de texto livre. As médias de compreensão e confiança são suprimidas quando a coorte
tem menos de cinco respostas (o mínimo pode aumentar por decisão de Privacy). O relatório inclui
contagens e cortes por categoria para evitar que uma média global esconda regressões.

Taxas vazias retornam `0` acompanhadas do denominador `0`; consumidores não devem interpretar esse
valor como qualidade comprovada. Métricas só autorizam promoção quando a amostra representativa e
os gates documentados forem revisados externamente.
