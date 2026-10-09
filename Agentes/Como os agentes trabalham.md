---
tipo: guia
---
# Como os agentes trabalham

Os agentes **não se chamam diretamente**. Eles conversam pelo [[Mural]]: cada recado é uma nota com
`de`, `para`, `status` e, quando é resposta, `responde`. Isso dá três coisas de graça:

1. **Histórico:** toda conversa fica no git e aparece no grafo do Obsidian.
2. **Assincronia:** um agente pode agir hoje e o outro amanhã, sem perder contexto.
3. **Supervisão humana:** qualquer recado para `arthur` é uma decisão que só ele toma.

## Ciclo de um agente
1. `cerebro mural --para <id>`: lê o que está esperando por ele.
2. Faz o trabalho, só nas pastas permitidas na nota dele.
3. Responde com `cerebro recado ... --responde "<recado>"` e fecha o original com `cerebro fechar`.
4. `cerebro validar`: links, campos do recado e ausência de dados sensíveis.

## Uma voz só para o Arthur
- Só o [[Maestro]] escreve para `arthur`. Isso é regra no **código** (`cerebro recado` recusa), não só no prompt.
- Cada recado carrega o `pedido` de origem (herdado pela resposta). No fim do ciclo, para cada pedido fica aberto
  só o recado mais recente para o Arthur; os anteriores viram `substituido`, com link para o novo.
- O que falta ele decidir fica na [[Caixa do Arthur]].

## Limites
- O cofre é **público**: nada de CPF, cartão, chave de API, dado de cliente ou de candidatura real.
- Número só com fonte (nota de projeto ou repositório).
- Ações fora do cofre (publicar, fazer deploy, mandar mensagem) viram recado para `arthur`.

Agentes: [[Maestro]], [[Secretario]], [[Carreira]], [[Dev]], [[Pesquisador]], [[Conteudo]], [[Marketing]], [[Operacao]], [[Critico]].
