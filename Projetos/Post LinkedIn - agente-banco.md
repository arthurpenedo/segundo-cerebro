---
tipo: rascunho
status: aprovado
autor: conteudo
---
# Post LinkedIn - agente-banco

Rascunho para o LinkedIn do Arthur. Projeto: [[agente-banco]]. Conceito: [[Regra no codigo, nao no prompt]]. Pedido: [[Post sobre o agente-banco]].

## Post

Se você escreve "só o gerente pode autorizar estorno grande" no prompt de uma IA, isso é um aviso na porta do cofre. Funciona se o modelo quiser obedecer.

Se a regra está no código da ferramenta, é uma fechadura. Mesmo que o modelo peça a coisa errada, o sistema recusa.

Foi isso que construí no agente-banco, um atendente de banco com IA que usa 10 ferramentas (saldo, boletos, contestação, protocolo, transferência para humano...). Cinco regras ficam no código, como o limite de R$ 100 para estorno na hora. Acima disso, a ferramenta não estorna: abre um protocolo e passa para uma pessoa.

Como provei? Com 19 testes automatizados, todos passando. Em um deles, um modelo simulado, com roteiro fixo, tenta estornar R$ 1.500: com a regra no código, bloqueia; sem ela, passa.

Também avaliei o agente em 41 cenários, olhando o estado final do banco de dados, e não o texto da resposta. Custo: zero, tudo com modelos abertos rodando no GitHub Actions.

Detalhe honesto: os modelos pequenos nunca tentaram a ação proibida, então a taxa de acerto empatou. Quem prova a trava é o teste.

Código e relatório: https://github.com/arthurpenedo/agente-banco

## Fontes dos números

- 10 ferramentas → [[2026-10-09 dev para conteudo numeros-do-agente-banco-com-fonte]] (item 3)
- 5 regras no código; limite de R$ 100 → mesmo recado (item 2)
- 19 testes passando; estorno de R$ 1.500 bloqueado com a regra e liberado sem ela → mesmo recado (itens 1 e 4)
- 41 cenários, avaliados pelo estado final do banco → mesmo recado (itens 1 e 4)
- Custo zero, modelos abertos no GitHub Actions → mesmo recado (item 5)
- Empate de taxa de acerto (modelos não tentaram a ação proibida) → mesmo recado (item 4); conceito em [[Regra no codigo, nao no prompt]]
- Link do repositório → mesmo recado (item 6)

Revisado por [[Critico]]: [[2026-10-09 critico para conteudo post-do-agente-banco-aprovado]]
