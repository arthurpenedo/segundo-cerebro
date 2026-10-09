---
tipo: projeto
repo: https://github.com/arthurpenedo/agente-banco
dono: dev
---
# agente-banco

Agente de atendimento bancário com 10 ferramentas; regra de negócio aplicada no código e avaliação pelo estado final do banco (41 cenários).

**Números (fonte: README do repositório):** Qwen 2.5 3B: 39% → 49% das tarefas resolvidas (v1 → v2), 0 violações de política.

**Mais números (fonte: README, `pytest -q` e `resultados/v2` em 09/out/2026):** 19 testes passando; 5 regras verificadas no código das ferramentas (alçada de R$ 100, tarifa contratual, transação já contestada, boleto pago, limite de 3 segundas vias) além do escopo ao cliente autenticado; custo de API zero (modelos abertos no GitHub Actions). Com a regra no código ou só no prompt, o 3B teve a mesma taxa na v2 (49%); a prova da regra está nos testes, não na taxa.

**Conceitos:** [[Tool calling]] [[Avaliacao de agentes]]

Repositório: https://github.com/arthurpenedo/agente-banco
