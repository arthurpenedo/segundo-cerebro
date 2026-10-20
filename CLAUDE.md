# segundo-cerebro: regras para qualquer agente

Este repositório é um **cofre do Obsidian**. As notas em Markdown são, ao mesmo tempo, a memória e o espaço de
trabalho dos agentes. Comece por `Inicio.md` e `Agentes/Como os agentes trabalham.md`.

- **Agentes:** cada um tem uma nota em `Agentes/` (papel, o que lê, onde escreve) e um subagente em `.claude/agents/`.
  A nota no cofre é a fonte da verdade: o Arthur edita o comportamento do agente pelo Obsidian.
- **Conversa:** só pelo Mural, com `cerebro recado` / `cerebro mural` / `cerebro fechar`. Nada de escrever na pasta de outro agente.
- **Público:** este cofre é vitrine. Nunca escreva CPF, cartão, chave de API, dado de cliente ou candidatura real.
  `cerebro validar` barra os casos óbvios, mas a responsabilidade é de quem escreve.
- **Números:** só com fonte (nota de projeto ou README do repositório).
- **Uma voz só para o Arthur:** só o `maestro` escreve recado para `arthur` (o `cerebro recado` recusa os outros). Os demais entregam o resultado ao maestro.
- **Pedido:** recado que começa um pedido da Entrada leva `--pedido "<nome da nota>"`; as respostas herdam sozinhas via `--responde`. No fim do ciclo, só o recado mais recente de cada pedido fica aberto para o Arthur, na [[Caixa do Arthur]].
- **Fora do cofre** (publicar, deploy, mandar mensagem, gastar dinheiro): vira recado para `arthur`.
- **Comandos:** um por vez, sem encadear. Texto longo de recado vai por arquivo: `--texto-arquivo .rascunhos/<nome>.txt`.
- **Laço automático:** `cerebro rodar` acorda o agente com recado aberto mais antigo até sobrar só recado para `arthur`.
  Com `--motor ollama` os agentes usam as ferramentas da `Bancada` (`ferramentas.py`), que aplicam estas regras no código.
- **Busca:** `cerebro buscar "<termos>"` acha a nota certa antes de escrever uma nova.
- Antes de terminar: `cerebro validar` precisa passar.

Instalação das ferramentas: `pip install -e .` (comando `cerebro`).
