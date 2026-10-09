---
tipo: conceito
---
# Revisão para entrevista: agentes com ferramentas

**O que é:** roteiro do que revisar antes da entrevista da [[Vaga ficticia - Dev de agentes de IA]]. Cada ponto aponta para uma nota de conceito e para o projeto que serve de evidência.

**O que revisar (nesta ordem):**
1. [[Tool calling]]: o modelo só pede a chamada; quem executa e decide é o código.
2. [[Regra no codigo, nao no prompt]]: prompt é pedido, código é trava. Saiba explicar o cuidado: com modelos pequenos o resultado empatou (49% nas duas versões), e a prova da regra está nos testes com modelo roteirizado, não na taxa.
3. [[Avaliacao de agentes]]: medir pelo estado final do banco, não pelo texto da resposta.
4. [[OWASP LLM Top 10]]: categorias de risco, como prompt injection.
5. [[LGPD]]: o que o projeto [[lgpd-guard]] cobre.

**Onde usei:** [[agente-banco]] (10 ferramentas, 41 cenários, 19 testes, 5 regras no código, 39% → 49% com 0 violações de política, números do README do repositório), [[redteam-br]] e [[lgpd-guard]].

**Cuidado:** não citar número que não esteja nas notas de projeto. Detalhes de [[redteam-br]], [[lgpd-guard]], [[bypenas-pedidos-n8n]] e [[resolvoja]] não foram consultados por mim: não verificado.

**Fontes:**
- [[agente-banco]] (README do repositório, `pytest -q` e `resultados/v2` em 09/out/2026), via nota de projeto.
- [[Regra no codigo, nao no prompt]] (README e `ferramentas.py` do repositório).
