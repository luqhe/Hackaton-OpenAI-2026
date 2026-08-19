# Minuta de consentimento do responsável e assentimento do menor

> Roadmap: R5-02  
> Status: minuta para revisão; não aprovada para participantes  
> Versão do pacote: 2026-08-19.draft-1

## Antes de decidir

O Guardian é um alpha supervisionado de proteção e letramento digital. Participar é voluntário.
O responsável pode retirar a família sem penalidade, e a criança/adolescente deve receber uma
explicação adequada à idade e poder expressar dúvidas ou desconforto. Este texto não substitui
os requisitos de consentimento/assentimento que a revisão aplicável determinar.

O alpha não é serviço de emergência, não substitui supervisão familiar e pode classificar uma
situação incorretamente. Na primeira fase, o sistema opera apenas com telemetria técnica e
`SHADOW`, sem alertar ou bloquear aplicativos.

## O que será avaliado

- funcionamento do onboarding e das permissões do agente;
- saúde, versão e fila offline do agente;
- tempo entre uma decisão sintética e o reconhecimento do comando;
- classificação em shadow mode, sem intervenção na primeira fase;
- compreensão das explicações e controles de transparência;
- processo de suporte, retirada e exclusão.

## Dados previstos e minimização

O agente pode acessar tela atual, texto visível, aplicativo e janela ativa para produzir contexto
temporário. Material seguro deve ser descartado após análise. Somente evidência mínima de um
incidente autorizado pode ser persistida. Telemetria técnica inclui versão, permissões, saúde,
contadores e latências; ela não deve conter texto ou imagem observada.

O Guardian não coleta câmera ou microfone, não oferece tela ao vivo e não deve armazenar um
histórico contínuo da tela. Dados do alpha não serão usados para treinar modelos sem um programa
separado, base apropriada e autorização explícita.

## Riscos e controles

Os riscos incluem classificação incorreta, indisponibilidade, consumo de recursos e exposição
indevida de dados. Controles planejados incluem coleta mínima, isolamento por família,
credenciais revogáveis, evidência privada, kill switches, plantão e interrupção imediata. Se um
controle obrigatório não estiver disponível, a sessão não começa ou é interrompida.

## Escolhas e retirada

Antes da participação, o responsável deve poder aceitar ou recusar separadamente a participação,
a persistência de evidência mínima e qualquer contato de pesquisa. A criança deve conhecer o
indicador de atividade, o que é observado e como pedir ajuda ou retirada.

Uma solicitação de retirada interrompe novas coletas e abre exclusão verificável dos dados da
família, incluindo evidências e credenciais. Prazos, exceções legais e tratamento de backups
precisam ser definidos na versão aprovada do pacote.

## Confirmações que a versão aprovada deverá registrar

- identidade do responsável e relação/autorização aplicável;
- família, criança, dispositivos, versão do texto e data/hora;
- jurisdição e faixa etária consideradas pela revisão;
- escolhas granulares e canal de retirada;
- assentimento ou registro apropriado à idade;
- quem apresentou as informações e respondeu às dúvidas.

Nenhum aceite deve ser coletado com esta minuta. A versão utilizável precisa de aprovação
registrada de Legal, Privacy e Product Safety em `config/pilot/legal-approvals.v1.json`.
