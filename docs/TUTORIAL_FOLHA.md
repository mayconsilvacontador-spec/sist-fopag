# Tutorial — do cadastro do servidor até a folha de pagamento

SIST FOPAG · PREVIBAM

> **Antes de começar: qual folha o SIST gera?**
> O SIST gera a **folha de benefícios do RPPS**: aposentadorias e pensões pagas pela PREVIBAM. A folha dos
> servidores **em atividade** (salários) é feita pela Prefeitura e pelos órgãos, e não pelo SIST.
>
> Por isso, o caminho é este:
>
> **servidor cadastrado → vínculo → processo no Protocolo → concessão da aposentadoria → implantação →
> folha de benefícios**
>
> Na pensão por morte, o caminho é o mesmo. A diferença é que a concessão é aberta para o instituidor (o servidor
> ou aposentado que faleceu) e o benefício nasce para cada dependente.

Os passos abaixo usam os nomes exatos dos menus e botões do sistema.

---

## Parte 0 — Preparação (uma vez só)

Quase tudo já está carregado no seu banco: planos FIN e PREV, as três folhas, 16 regras de aposentadoria,
18 rubricas, tabelas de IR, alíquota de 14% e cadastros básicos. Confira apenas o que segue.

| O quê | Onde | Situação hoje |
|---|---|---|
| **Teto do RGPS de 2026** | Administração › Parâmetros › `rgps.teto` | **Falta cadastrar.** Sem ele, a folha de 2026 usa o teto de 2025 e mostra um aviso |
| Ente, órgãos, cargos, bancos | Gestão de Cadastros › Entes / Órgãos / Cargos / Bancos | Já existem; inclua os que faltarem |
| Setor e tipo de processo do Protocolo | Protocolo › Configuração › **Novo setor** / **Novo tipo** | Há 1 setor e 1 tipo. **Você precisa ser membro do setor** para abrir processos nele |
| **Usuários de cada setor** | Administração › Usuários | Crie usuários com os perfis **Previdenciário** (Benefícios), **Procuradoria Jurídica**, **Controle Interno**, **Presidência** e **Folha**. Por segurança, uma só pessoa não conclui a concessão inteira |
| Exercício e competência | — | Não precisa: a folha cria a competência sozinha |

---

## Parte 1 — Cadastrar o servidor

### 1. Pessoa (Cadastro Único)

1. Vá em **Gestão de Cadastros › Cadastro Único** e clique em **Nova pessoa**.
2. Preencha CPF, nome, data de nascimento e sexo. Quando a consulta à Receita (Conecta gov.br) estiver
   configurada, os dados podem ser trazidos pelo CPF.
3. Preencha também **raça/cor** (pedida pelo eSocial).
4. Salve. A ficha da pessoa abre com várias abas.

### 2. Endereço e conta bancária (na ficha da pessoa)

- Aba de endereços: **Novo endereço**. Informe também o **código IBGE do município** (Barra Mansa: 3300407).
- Aba de contas: **Nova conta**, com banco, agência, conta e dígitos.

**Sem conta bancária, o benefício é calculado, mas fica de fora do arquivo de pagamento do banco.**

### 3. Dependentes (se houver)

Use a aba de dependentes da ficha. Marque **dependente para IR** quando for o caso: isso reduz o IR na folha.

### 4. Vínculo (servidor efetivo)

1. Na ficha da pessoa, abra a aba de vínculos e clique em **Novo vínculo**.
2. Preencha:
   - **Órgão**, **Matrícula**, **Cargo atual**;
   - as datas de ingresso: **Ingresso no serviço público**, **Ingresso no ente**, **Ingresso na carreira**,
     **Início no cargo atual**;
   - **Vencimento base (R$)**;
   - **Massa (fundo)**: Financeiro, Previdenciário ou Compra de Vidas. **É ela que define em qual das três folhas
     o servidor será pago quando se aposentar.**

### 5. Tempo e salários (Gestão Previdenciária)

- **Histórico Contributivo:** lance os salários de contribuição. Eles são **obrigatórios nas regras que calculam
  pela média**. Nas regras com integralidade, basta a remuneração do vínculo.
- **Averbações:** tempo de outros regimes (INSS, outro RPPS), se houver.
- **Simulação de Aposentadoria:** escolha a pessoa e veja quais regras ela já cumpre e em que data.

---

## Parte 2 — Conceder a aposentadoria

### 6. Abrir o processo no Protocolo

1. Vá em **Protocolo › Processos** e clique em **Abrir processo**.
2. Preencha:
   - **Tipo de processo** (ex.: Aposentadoria);
   - **Setor de abertura**;
   - **Assunto**;
   - **Interessado**: escolha a pessoa.
3. Clique em **Abrir processo**. O processo fica "em tramitação", com prazo contado automaticamente.

### 7. Abrir a concessão

1. Vá em **Concessão de Benefícios › Aposentadoria** e clique em **Nova concessão**.
2. Escolha o servidor e o processo aberto no passo 6. Clique em **Abrir concessão**.

### 8. Seguir as etapas na tela da concessão

A barra no alto mostra a etapa e **qual setor** deve agir. O fluxo segue o mapeamento da PREVIBAM, e **cada setor
só vê os botões da sua etapa**.

| Etapa | Quem faz | O que fazer |
|---|---|---|
| **Enquadramento** | Benefícios | Informe a data de validade (início da aposentadoria), a classificação dessa data e a **regra**. Só aparecem as regras cumpridas naquela data. Clique em **Confirmar enquadramento** |
| **Cálculo** | Benefícios | Clique em **Calcular proventos**, confira as parcelas (se precisar, **Ajustar parcelas**) e clique em **Enviar ao Jurídico** |
| **Parecer** | Procuradoria Jurídica | Escreva o parecer: **Parecer favorável** ou **Devolver para correção**. O favorável gera a **minuta de portaria** |
| **Conformidade** | Controle Interno | Confira as regras e o cálculo: **Conforme** ou **Não conforme — devolver** |
| **Assinatura** | Presidência | Confira a minuta, informe número e data e clique em **Assinar portaria** (ou **Indeferir**). A **portaria** é gerada |
| **Publicação** | Folha de Pagamento | Informe a data e o meio de publicação (Notícia Oficial). Clique em **Registrar publicação** |
| **Implantação** | Folha de Pagamento | Clique em **Implantar na folha** |
| **TCE-RJ** | COMPREV / Presidência | Registre o envio ao TCE-RJ e o julgamento. Se for **ilegal**, a Presidência anula |

**Salvaguardas:**
- **Assinatura eletrônica:** parecer, conformidade, assinatura, indeferimento, implantação e anulação pedem a
  **senha** de quem pratica o ato. Fica registrado na **Trilha do processo**, com nome, data, hora e código.
- **Segregação de funções:** a mesma pessoa não pode instruir, dar parecer, conferir e assinar o mesmo processo,
  e quem instruiu não implanta.
- **Valores fixados:** na assinatura os valores ficam fixados. Se algo mudar depois, a implantação é bloqueada.
- **Documentos automáticos:** a minuta (após o parecer favorável), a portaria (na assinatura), o ofício de
  indeferimento e a minuta de anulação são gerados em Word. Eles aparecem em **Documentos gerados**, ficam anexados ao
  processo do Protocolo e são avisados ao setor de Benefícios na **Central de Alertas**.
- **Modelos de texto:** a redação fica em **Concessão › Modelos de portaria**, com marcadores como {nome} e {valor}.
- **Revisão de valor:** não é mais feita direto no benefício. Use **Concessão › Revisão**, que segue
  Jurídico → Presidência (portaria) → publicação → folha.

Na **Implantação**, o sistema:
- cria o benefício na folha da massa do vínculo;
- encerra o vínculo como aposentado;
- registra o histórico.
Para conferir, abra **Folha de Benefícios › Beneficiários**.

> **Atalho para testes:** os benefícios trazidos pela importação (base SPREV) ficam em
> **Folha de Benefícios › Beneficiários**, aba **Importados aguardando implantação**. O botão **Implantar todos**
> põe todos na folha de uma vez (pede sua senha).
>
> **Atenção:** a sua base atual é a fictícia. O que for implantado fica registrado, porque o sistema não apaga
> histórico. Use esse atalho só em ambiente de testes.

---

## Parte 3 — Gerar a folha

### 9. Lançamentos do mês (opcional)

Faça isto **antes** de calcular a folha:

| Menu | Para quê |
|---|---|
| **Folha de Benefícios › Diferenças** | Diferenças de proventos, reposições ao erário, descontos judiciais |
| **Consignações** (e **Consignatárias**) | Empréstimos e mensalidades, respeitando a margem de 35% |
| **Pensão Alimentícia** | Percentual do bruto ou do líquido, ou valor fixo |
| **Isenção de IR (moléstia grave)** | Laudo oficial que isenta do IR |

### 10. Abrir e calcular

1. Vá em **Folha de Benefícios › Folha Mensal** e clique em **Abrir folha**.
2. Escolha a **folha (massa)** (FIN, PREV ou PREV-CV), o **mês** e o **ano**.
3. Na tela da folha, clique em **Calcular**. O sistema faz:
   - proventos proporcionais aos dias;
   - retroativo, na primeira folha de um benefício concedido no SIST;
   - contribuição de 14% sobre o que passa do teto do RGPS;
   - IRRF: deduções legais ou desconto simplificado, isenção acima de 65 anos e redução da Lei 15.270/2025;
   - pensão alimentícia e consignações.
4. Repita para cada massa. **Cada massa tem a sua folha, e os meses não podem ser pulados.**

### 11. Conferir

Ainda na tela da folha:

| Aba | O que mostra |
|---|---|
| **Contracheques** | Lista de todos; clique para ver o contracheque. Marque **Somente com avisos** para ver só os problemas |
| **Conferência** | Comparação com o mês anterior: entradas, saídas e variações de 5% ou mais |
| **Resumo por rubrica** | Totais por rubrica, com exportação para planilha |

Se mudar algum cadastro ou lançamento, clique em **Recalcular**. Quando estiver tudo certo, clique em
**Marcar como conferida**.

### 12. Fechar

Clique em **Fechar folha**. Depois de fechada:
- a folha não é mais recalculada;
- as parcelas de consignações avançam;
- para corrigir, use **Reabrir**, que pede justificativa e fica registrado.

### 13. Pagar

**Opção A — pelo arquivo do banco:**
1. Em **Gestão Financeira › Bancos**, cadastre a conta pagadora do **mesmo plano** da folha.
2. Em **Gestão Financeira › Pagamentos**, clique em **Novo lote** e escolha a folha, a conta e a data do crédito.
3. Clique em **Aprovar** e depois em **Gerar arquivo CNAB 240**.
4. Envie o arquivo ao banco.
5. Quando o banco devolver o retorno, importe-o em **Gestão Financeira › Arquivos Bancários**.
6. Quando todos estiverem pagos, a folha passa a **PAGA** sozinha. Quem foi rejeitado entra no próximo lote.

**Atenção:** o arquivo CNAB precisa ser **homologado com o banco** antes do primeiro uso.

**Opção B — sem arquivo:** na tela da folha, clique em **Registrar pagamento** e informe a data.

### 14. Depois da folha

| Menu | Para quê |
|---|---|
| **Folha de Benefícios › Contracheques** | Contracheques por beneficiário, com impressão |
| **Informe de Rendimentos** | Comprovante anual para o IR (considera só folhas fechadas ou pagas) |
| **Arrecadação › Contribuição do Servidor** › **Registrar retenções da folha** | Lança como receita a contribuição descontada dos aposentados |
| **eSocial RPPS › S-1207** › **Gerar S-1207 / S-1210 da folha** | Eventos do eSocial da folha (exportados para transmitir com o certificado digital) |
| **Gestão Financeira › Integração Contábil** | Lançamentos contábeis do mês |
| **Portal do Segurado** | Veja a Parte 4 |

### 15. 13º salário (novembro ou dezembro)

1. Vá em **Folha de Benefícios › 13º Salário** e clique em **Abrir folha**.
2. Siga os mesmos passos de calcular, conferir, fechar e pagar.

---

## Parte 4 — Portal do Segurado

1. Vá em **Portal do Segurado** (menu interno) e clique em **Liberar acesso**.
2. Escolha a pessoa e clique em **Gerar senha provisória**. A senha aparece **uma única vez**: entregue ao segurado
   de forma segura, junto com o endereço **/segurado** (ex.: `http://localhost:3000/segurado` nesta máquina).
3. O segurado entra com **CPF e senha**. No primeiro acesso, ele cria a própria senha.
4. No portal, o segurado vê:
   - dados cadastrais e benefícios;
   - **contracheques** (só de folhas fechadas ou pagas);
   - **informe de rendimentos**;
   - **processos** no Protocolo;
   - **solicitações**: atualização cadastral, requerimentos e dúvidas.
5. As solicitações chegam na aba **Solicitações** do menu interno **Portal do Segurado**, onde a equipe responde.

---

## Problemas comuns

| Mensagem | O que fazer |
|---|---|
| "Teto do RGPS de 2026 não cadastrado" | Cadastre `rgps.teto` de 2026 em Administração › Parâmetros |
| "Não foi possível calcular: cadastre os salários de contribuição" | Lance os salários em Gestão Previdenciária › Histórico Contributivo, ou o vencimento base no vínculo |
| "Feche antes a folha MM/AAAA desta massa" | A folha do mês anterior ainda está aberta |
| "A próxima folha mensal de … é MM/AAAA" | Não se pula mês: abra a competência indicada |
| Beneficiário fora do lote de pagamento | Cadastre a conta bancária da pessoa e crie um novo lote |
| Botão **Abrir processo** desabilitado | Não há setor disponível: confira em Protocolo › Configuração se o setor existe e se você é membro dele |
