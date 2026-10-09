---
tipo: preparacao
vaga: "[[Vaga ficticia - Dev de agentes de IA]]"
status: rascunho
criado: '2026-10-09'
---
# Entrevista: 3 perguntas técnicas mais prováveis

Vaga fictícia: [[Vaga ficticia - Dev de agentes de IA]]. Pedido em [[Preparar entrevista da vaga ficticia]]. Para revisar o conceito antes: [[Regra no codigo, nao no prompt]], [[Tool calling]], [[OWASP LLM Top 10]], [[LGPD]]. Nota do Pesquisador sobre o que revisar: [[Revisao para entrevista - agentes com ferramentas]].

## 1. Como você impede que um agente com ferramentas faça o que não deve?
Coloco a regra no código da ferramenta, não só no prompt: prompt é pedido, código é trava. No [[agente-banco]] são 10 ferramentas e 5 regras verificadas no código (por exemplo, alçada de R$ 100 no estorno), além do escopo ao cliente autenticado. Quando a ferramenta recusa, devolve o próximo passo: abrir protocolo e transferir para um humano (fonte: [[Post LinkedIn - agente-banco]]). Os 19 testes passam; com modelo 3B a taxa foi igual com a regra no código ou só no prompt (49%), então a prova está nos testes, não na taxa.

## 2. Como você mede se um agente melhorou?
Avalio pelo estado final do banco, não pelo texto da resposta. No [[agente-banco]], 41 cenários: Qwen 2.5 3B foi de 39% para 49% das tarefas resolvidas (v1 → v2), com 0 violações de política (fonte: README). Custo de API zero, com modelos abertos no GitHub Actions. Veja [[Avaliacao de agentes]].

## 3. Como você trata segurança de LLM e dados pessoais?
Duas frentes medidas. Segurança: no [[redteam-br]], 30 ataques do OWASP LLM Top 10 e 7 técnicas de mutação; a taxa de sucesso dos ataques foi de 36% (sem defesa) para 29% (prompt) e 0% (defesa completa), com 0 falsos positivos. Dados: o [[lgpd-guard]] pseudonimiza dados pessoais num proxy compatível com a API da OpenAI; F1 0,94 contra 0,60 do Presidio no conjunto desafio (fontes: READMEs).
Mostra que prompt sozinho reduz pouco; a defesa em camadas é que zera.

## Para você levar
- Se perguntarem de WhatsApp: [[bypenas-pedidos-n8n]]; produção: [[resolvoja]]. Não escrevi números deles aqui por não ter conferido a fonte.
