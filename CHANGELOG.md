# Changelog

## 1.0.0 · 20/10/2026

- **Motor próprio de agentes** (`agente.py`, `ferramentas.py`, `llm.py`): os agentes rodam com qualquer modelo
  compatível com a API da OpenAI (Ollama, vLLM, OpenAI) com tool calling. O Claude Code continua disponível.
- **Bancada com regras no código:** remetente fixo, só o maestro fala com o humano, cada agente fecha só os recados
  dele e escreve só nas pastas de `escreve_em`, e o sistema barra dado sensível. Toda chamada fica auditada.
- **Trilha no Diário:** a nota `Execucao` mostra as ferramentas, as recusas e os tokens de cada turno.
- **Busca BM25** (`cerebro buscar`) usada pelos agentes e pelo MCP.
- **Servidor MCP** (`cerebro mcp`): buscar, ler, mural, caixa, fazer pedido, decidir, validar, mais o resource
  `cerebro://caixa` e o prompt `revisar_caixa`.
- **`cerebro init`**: cofre novo com os 9 agentes; `CEREBRO_HUMANO` troca o nome de quem decide.
- **Avaliação** (`cerebro avaliar`, workflow `Avaliação`): 5 cenários com `qwen2.5:3b` e `qwen2.5:7b` no CI. O
  painel mostra as métricas.
- **CI:** Linux e Windows, Python 3.11 e 3.13, ruff e cobertura mínima de 80%.
- `cerebro turno <agente>`: acorda um agente uma vez e mostra cada ferramenta usada.

## 0.1.0 · 09/10/2026

- Cofre do Obsidian com 9 agentes, Mural de recados, laço com Claude Code, Caixa do Arthur, painel no Pages.
