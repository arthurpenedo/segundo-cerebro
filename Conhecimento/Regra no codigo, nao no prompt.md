---
tipo: conceito
---
# Regra no código, não no prompt

**O que é:** Uma regra que só está escrita no prompt (as instruções em texto dadas ao modelo) é um pedido: o modelo pode
ignorá-la, esquecê-la ou ser convencido a quebrá-la. Uma regra que está no código da ferramenta que executa a ação é uma
trava: mesmo que o modelo peça a coisa errada, o sistema recusa.

**Analogia:** é a diferença entre um aviso na porta do cofre ("só o gerente abre") e uma fechadura que só abre com a
chave do gerente. O aviso depende da boa vontade de quem passa; a fechadura não depende de ninguém.

**Exemplo concreto:** no atendimento bancário, a regra é "estorno na hora só até R$ 100". O cliente pede o estorno de
R$ 1.500. Se a regra está só no prompt, o modelo pode ceder. No código, a ferramenta de contestação compara o valor com
o limite (`ALCADA_ESTORNO = 100.00`); acima disso não estorna, marca como "em análise" e devolve ao modelo o próximo passo
("abra um protocolo e transfira para um humano"). Ou seja, o erro volta como mensagem e o modelo consegue seguir a partir dali.

**Cuidado com a conclusão:** nos testes com modelos pequenos, política no código e política só no prompt empataram, porque
os modelos nunca chegaram a tentar a ação proibida. A proteção foi provada em teste com um modelo roteirizado que tenta
estornar R$ 1.500: com a verificação na ferramenta o estorno é bloqueado; sem ela, passa (segundo o README).

**Onde usei:** [[agente-banco]] (veja também [[Tool calling]]).

**Fontes:**
- README do repositório https://github.com/arthurpenedo/agente-banco (seções "Decisões técnicas" e "O que os números mostram"), consultado.
- `src/agente_banco/ferramentas.py` do mesmo repositório (docstring do módulo, `ALCADA_ESTORNO` e `_contestar_cobranca`), consultado.
- A frase "o que está só no prompt é sugestão" vem do README, que a atribui ao projeto redteam-br; esse projeto não foi consultado por mim: não verificado.
