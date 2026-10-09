# segundo-cerebro

[![CI](https://github.com/arthurpenedo/segundo-cerebro/actions/workflows/ci.yml/badge.svg)](https://github.com/arthurpenedo/segundo-cerebro/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Obsidian](https://img.shields.io/badge/Obsidian-cofre-7c5cff)
![License](https://img.shields.io/badge/license-MIT-green)

> **Um segundo cérebro onde agentes de IA trabalham juntos.** É um cofre do Obsidian (uma pasta de notas em
> Markdown) em que 9 agentes do Claude Code têm cada um seu papel e **conversam por recados** num Mural. Toda
> conversa vira nota, fica versionada no git e aparece no grafo do Obsidian. O CI valida o cofre a cada commit
> e publica um painel com os agentes, as conversas e o grafo.

**Painel ao vivo:** [arthurpenedo.github.io/segundo-cerebro](https://arthurpenedo.github.io/segundo-cerebro/)

![Painel do segundo-cerebro](docs/painel.png)

## A ideia

Sistemas multiagente costumam esconder a conversa entre os agentes dentro de um processo: quando termina, sobra
só a resposta final. Aqui a conversa **é o produto**. Os agentes não se chamam diretamente; cada um lê os
recados abertos para ele, faz o seu trabalho e deixa recado para quem age em seguida. Isso dá três coisas:

1. **Histórico auditável.** Dá para ver quem pediu o quê, quem respondeu com qual fonte e quem aprovou.
2. **Supervisão humana de verdade.** Qualquer ação fora do cofre (publicar, fazer deploy, gastar dinheiro) vira
   um recado para `arthur`. O agente não executa, só prepara.
3. **Comportamento editável pelo Obsidian.** O papel e as regras de cada agente ficam numa nota em `Agentes/`.
   O arquivo do subagente em `.claude/agents/` só aponta para ela. Mudar o agente é editar uma nota.

## Os agentes

| Agente | Papel | Escreve em |
|---|---|---|
| **Maestro** | Quebra o pedido em recados com dono e fecha o ciclo com o Arthur | Mural |
| **Secretário** | Organiza a Entrada e escreve o Diário | Diario, Mural, 00-Entrada |
| **Dev** | Números e status dos repositórios, sempre com fonte | Projetos, Mural |
| **Pesquisador** | Notas de conceito com analogia e fonte | Conhecimento, Mural |
| **Conteúdo** | Posts de LinkedIn e roteiros | Projetos, Mural |
| **Crítico** | Confere cada número e afirmação; responde "aprovado" ou "ajustar" | Mural |
| **Carreira** | Vagas, entrevistas, currículo por vaga (fictícias neste cofre público) | Carreira, Mural |
| **Marketing** | Campanhas da By.penas | Projetos, Mural |
| **Operação** | Status da Resolvoja em produção | Projetos, Mural |

## Uma conversa real

O primeiro ciclo está todo no [Mural](Mural/) e no [Diário de 09/10/2026](Diario/2026-10-09.md). O pedido foi
*"um post de LinkedIn sobre o agente-banco, com os números reais"*:

1. O **Maestro** delegou: o post para o Conteúdo e o conceito para o Pesquisador.
2. O **Conteúdo** não escreveu nada antes de pedir ao **Dev** os números, cada um com fonte.
3. O **Dev** respondeu com 6 números conferidos no repositório e **dois avisos**: a taxa de acerto do agente
   empatou entre "regra no código" e "regra no prompt", então o post não podia dizer que o código venceu. E um
   comentário no código cita uma regra que não está implementada, então ela não podia aparecer no post.
4. O **Pesquisador** escreveu a nota [Regra no código, não no prompt](Conhecimento/Regra%20no%20codigo%2C%20nao%20no%20prompt.md),
   com a analogia "aviso na porta × fechadura", e chegou de forma independente ao mesmo alerta do empate.
5. O **Conteúdo** escreveu o rascunho, com uma seção "Fontes dos números" ligando cada número ao recado do Dev.
6. O **Crítico** conferiu cada afirmação contra o código (incluindo o teste do estorno de R$ 1.500) e aprovou,
   com dois ajustes de linguagem para leigos.
7. O **Maestro** fechou o ciclo com um recado para o Arthur, a única pessoa que pode publicar.

Resultado: [o post](Projetos/Post%20LinkedIn%20-%20agente-banco.md) e um achado real de código no outro projeto,
que nenhum agente teria feito sozinho no papel de "escritor".

## Como funciona por dentro

```
cerebro mural --para dev                 # o que está esperando pelo agente
cerebro recado --de dev --para conteudo --assunto "..." --texto "..." --responde "<recado>"
cerebro fechar "Mural/<recado>.md"       # aberto -> feito
cerebro validar                          # roda no CI
cerebro painel --html site/index.html    # painel do Pages
```

- **Recado** = nota em `Mural/` com frontmatter `de`, `para`, `status`, `criado`, `assunto` e, quando é
  resposta, `responde`. Os fios de conversa são montados por `responde`.
- **`cerebro validar`** quebra o build se houver link `[[...]]` sem destino, recado sem campo obrigatório ou para
  agente que não existe, agente sem papel, ou **dado sensível** (CPF, cartão, chave de API), porque o cofre é público.
- **Painel:** HTML estático com os agentes, as conversas e o grafo de notas (d3), publicado no GitHub Pages pelo CI.
- **Custo:** zero de API. Os agentes rodam na assinatura do Claude Code; o CI só roda Python.

## Rodar

```bash
pip install -e ".[dev]"
pytest -q            # 5 testes
cerebro validar
```

Para abrir como segundo cérebro: Obsidian → *Abrir pasta como cofre* → esta pasta. Para pôr os agentes para
trabalhar: abra o Claude Code nesta pasta, escreva um pedido em `00-Entrada/` e peça ao `maestro` para começar.

## Limites honestos

- A orquestração ainda é manual: alguém (eu, pelo Claude Code) chama o próximo agente. Um laço automático
  "enquanto houver recado aberto, acorde o destinatário" é o próximo passo.
- O validador de dados sensíveis usa padrões simples. Ele pega os casos óbvios, não substitui o
  [lgpd-guard](https://github.com/arthurpenedo/lgpd-guard).
- Carreira usa dados fictícios de propósito: este cofre é vitrine pública.

---

Feito por [Arthur Penedo](https://www.linkedin.com/in/arthurpenedo) · parte do portfólio de IA aplicada
([agente-banco](https://github.com/arthurpenedo/agente-banco), [lgpd-guard](https://github.com/arthurpenedo/lgpd-guard),
[redteam-br](https://github.com/arthurpenedo/redteam-br)).
