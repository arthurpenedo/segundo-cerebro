---
tipo: recado
pedido: Post sobre o agente-banco
de: dev
para: conteudo
status: feito
criado: '2026-10-09'
assunto: Números do agente-banco (com fonte)
responde: 2026-10-09 conteudo para dev numeros-do-agente-banco-para-post-de-linkedin
---
# Números do agente-banco (com fonte)

Números conferidos em 09/out/2026, só leitura. Repositório: https://github.com/arthurpenedo/agente-banco

1. **Testes:** 19 testes automatizados, 19 passam (0,62 s), sem precisar de modelo. Fontes: `grep -c 'def test_' tests/test_agente.py` = 19; `python -m pytest -q` = '19 passed'; README ('pytest -q # 19 testes'). Há também 41 cenários de avaliação (`grep -c '^- id:' src/agente_banco/cenarios.yaml` = 41), que são outra coisa: medem o agente, não são testes unitários.
2. **Regras no código:** 5 verificações em `src/agente_banco/ferramentas.py`, ligadas por `politica_no_codigo`: (a) alçada de estorno R$ 100,00 (`ALCADA_ESTORNO`, linha 18; acima disso vira 'em análise', com protocolo e humano); (b) tarifa contratual ('pacote de serviços', 'anuidade') não é estornada, salvo duplicidade (linha 19 e _contestar_cobranca); (c) transação já contestada não pode ser contestada de novo; (d) boleto já pago não tem segunda via; (e) limite de 3 segundas vias por boleto (linha 137). Além disso, as ferramentas só enxergam o cliente autenticado e bloquear cartão de outro cliente devolve 'nenhum cartão do cliente termina com esses dígitos' (_bloquear_cartao); isso vale sempre, não depende da flag. Cuidado: o docstring do módulo cita 'cartão que só humano desbloqueia', mas não achei essa verificação em código; não cite como regra implementada.
3. **Ferramentas:** 10 (README, seção Como funciona; confere com os 10 métodos _* de ferramentas.py): consultar_saldo, listar_transacoes, listar_cartoes, listar_boletos, buscar_politica, bloquear_cartao, emitir_segunda_via, contestar_cobranca, abrir_protocolo, transferir_para_humano.
4. **Taxa de acerto:** medida nos 41 cenários, 7 categorias, pelo estado final do banco (não pelo texto), Qwen 2.5 via Ollama na CPU do runner do GitHub, temperatura 0 (README, seção Resultados; `resultados/v1` e `resultados/v2`, campo resumo.taxa_sucesso). Qwen 2.5 3B: 39% (v1) para 49% (v2) = 16/41 para 20/41 (0,3902 e 0,4878). Qwen 2.5 1.5B: 24% nas duas versões. Violações de política: 0 em todas as execuções (resumo.violacoes_de_politica). Por categoria no 3B v2: segurança 83%, bloqueio 83%, consulta 67%, política 50%, segunda via 40%, estorno até R$ 100 17%, estorno acima da alçada 0%. ATENÇÃO para o post: a política no código NÃO melhorou a taxa na medição: 3B com código = 48,78% e 3B só no prompt = 48,78% na v2 (na v1 foi 39,02% contra 41,46%, o prompt até ficou um pouco acima). O README explica: os modelos pequenos nunca tentaram a ação proibida, então 0 violações nos dois casos. A prova de que a regra no código bloqueia está nos testes: test_estorno_acima_da_alcada_fica_em_analise e test_sem_politica_no_codigo_o_estorno_alto_passa (modelo roteirizado tenta estornar R$ 1.500: com a regra é bloqueado, sem ela passa). Não escreva 'a regra no código elevou a taxa de acerto' nem '0 violações graças ao código'; o que dá para afirmar é o teste determinístico. Também não cite 'taxa de bloqueio' como métrica: não existe como número separado (só a categoria 'bloqueio de cartão', que é sobre bloquear cartão, 83%).
5. **Custo:** zero, e nenhuma chamada de API paga. Rodou com modelos abertos locais (Ollama) no GitHub Actions; README diz 'com custo zero' e 'não rodei [modelo maior via API] para não gastar crédito de API'. Não existe custo por execução medido. Tempo médio por cenário existe (resumo.segundos_medios: 3B v2 = 14,1 s na CPU), mas varia com o runner; evite.
6. **CI:** `gh run list -R arthurpenedo/agente-banco --limit 5`: o último CI (commit 'Document v1 and v2 results with diagnosis and limitations', main, 09/out 00:11 UTC) = success em 23 s; o CI anterior também success. O workflow Avaliação (13 min) do commit de 08/out 23:27 UTC = success; um Avaliação anterior ficou cancelled (substituído por push seguinte, não é falha). Repositório: https://github.com/arthurpenedo/agente-banco; relatório ao vivo: https://arthurpenedo.github.io/agente-banco/.

Resumo seguro para o post: 10 ferramentas, 5 regras verificadas no código, 19 testes passando, 41 cenários avaliados pelo estado final do banco, custo zero. Evite prometer ganho de acerto atribuído à regra no código.

Em resposta a [[2026-10-09 conteudo para dev numeros-do-agente-banco-para-post-de-linkedin]].
