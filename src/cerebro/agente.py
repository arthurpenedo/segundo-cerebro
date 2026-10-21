"""Um turno de agente com qualquer modelo de linguagem (motor próprio, sem depender do Claude Code).

O agente recebe como instrução de sistema a sua nota em Agentes/ (papel e regras, editáveis no Obsidian),
as regras gerais do cofre e o motivo de ter sido acordado. A partir daí conversa com o modelo: cada chamada
de ferramenta é executada pela `Bancada`, que aplica as regras no código e registra tudo.

O turno termina quando o modelo responde sem pedir ferramenta, ou no limite de passos (para nunca girar
em falso). Se o modelo esquecer de ler o Mural, o motor já entrega os recados abertos na primeira mensagem.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from .cofre import ler_cofre
from .ferramentas import Bancada, Registro, esquema_openai
from .llm import LLM
from .mural import HUMANO, abertos_para, agentes

REGRAS = f"""Você é um agente de um segundo cérebro (um cofre de notas do Obsidian). Você trabalha usando ferramentas.
Regras do cofre (aplicadas pelo sistema; se uma ferramenta recusar, leia o motivo e corrija):
- Converse com os outros agentes só por recados no Mural (`deixar_recado`), sempre respondendo ao recado que recebeu (`responde`).
- Só o maestro escreve para `{HUMANO}`. Os outros entregam o resultado final ao maestro.
- Escreva notas só nas suas pastas. Números só com fonte (nome da nota de onde saíram).
- O cofre é público: nunca escreva CPF, cartão, chave de API ou dado pessoal.
- Ações fora do cofre (publicar, gastar dinheiro, mandar mensagem) não são suas: viram recado para o maestro levar a {HUMANO}.
- Ao terminar o que é seu, feche os recados que tratou (`fechar_recado`) e responda em uma ou duas frases o que fez."""


@dataclass
class ResultadoTurno:
    agente: str
    resposta: str
    passos: int
    registros: list[Registro] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_saida: int = 0
    segundos: float = 0.0
    parou_no_limite: bool = False
    lembretes: int = 0

    @property
    def recusas(self) -> int:
        return sum(not r.ok for r in self.registros)


PROTOCOLO_MAESTRO = f"""Como você trabalha (maestro):
1. Pedido novo da Entrada: escolha na lista da equipe o agente cujo papel resolve o pedido e use deixar_recado
   para ele, explicando o que entregar e passando `pedido` com o nome da nota. Você não faz o trabalho.
2. Quando um agente responder com o resultado: deixe um recado para `{HUMANO}` (responde = o recado recebido)
   resumindo o que foi feito, com links [[...]] para as notas, e o que depende de decisão dele. Responder já resolve
   o recado recebido. Você só fecha recados endereçados a você; os que você enviou, quem recebe é que resolve.
3. Pedido que exige ação fora do cofre (publicar, postar, pagar, mandar mensagem): você não executa. Peça ao agente
   certo para preparar (ex.: o post) e leve a {HUMANO} como decisão para aprovar."""

PROTOCOLO_AGENTE = """Como você trabalha:
1. Para cada recado aberto para você: faça o trabalho pedido (se gerar conteúdo, salve com escrever_nota numa pasta sua).
2. Responda a quem pediu com deixar_recado (para = quem escreveu o recado, responde = nome do recado), com o
   resultado e o link [[...]] da nota. Responder já resolve o recado recebido.
3. Nunca mande recado para você mesmo. Só termine quando não houver recado aberto para você.
4. Revisão (crítico): responda "aprovado" ou "ajustar: <o quê>" uma única vez. "aprovado" vai direto para o maestro
   (o sistema encaminha). Quem recebe "ajustar" corrige uma vez e devolve ao crítico.
5. Números e fatos: copie da nota do cofre que é a fonte (veja "Notas do cofre ligadas a este pedido") e cite a nota.
   Nunca invente um número."""

TRADUCAO = ("Sua nota cita comandos de terminal; aqui você usa ferramentas: `cerebro mural` = ler_mural, "
            "`cerebro recado` = deixar_recado, `cerebro fechar` = fechar_recado, `cerebro validar` = não precisa.")


def instrucao_de_sistema(raiz: Path, agente: str) -> str:
    equipe = agentes(ler_cofre(raiz))
    ficha = equipe.get(agente)
    if ficha is None:
        raise ValueError(f"'{agente}' não é um agente do cofre")
    pastas = ", ".join(str(p) for p in ficha.meta.get("escreve_em") or [])
    lista = "\n".join(f"- {i}: {a.meta.get('papel', '')}" for i, a in sorted(equipe.items()))
    protocolo = PROTOCOLO_MAESTRO if agente == "maestro" else PROTOCOLO_AGENTE
    return (f"{REGRAS}\n\nHoje é {date.today().isoformat()}.\n\nVocê é o agente `{agente}` ({ficha.meta.get('nome', agente)}). Pode escrever em: {pastas}.\n\n"
            f"Equipe (id: papel):\n{lista}\n\n{protocolo}\n\n{TRADUCAO}\n\n"
            f"Sua nota no cofre (papel e regras):\n\n{ficha.corpo.strip()}")


def _abertos_meus(raiz: Path, agente: str) -> set[str]:
    return {r.nome for r in abertos_para(ler_cofre(raiz), agente)}


def notas_do_pedido(raiz: Path, consulta: str, limite: int = 3, tamanho: int = 700) -> str:
    """As notas de conhecimento do cofre mais ligadas ao pedido, com o começo do texto (para o agente não inventar)."""
    from .busca import Indice

    fora = {"mural", "agentes", "00-entrada", "diario"}
    notas = {k: n for k, n in ler_cofre(raiz).items() if n.pasta.lower() not in fora and n.tipo != "recado"}
    achados = [r for r in Indice(notas).buscar(consulta, limite=limite) if r.pontos > 0] if consulta.strip() else []
    if not achados:
        return ""
    partes = [f"### [[{r.nota.nome}]] ({r.nota.pasta or 'raiz'})\n{r.nota.corpo.strip()[:tamanho]}" for r in achados]
    return "Notas do cofre ligadas a este pedido (use como fonte; cite o nome da nota):\n\n" + "\n\n".join(partes)


def sugerir_agentes(raiz: Path, pedido: str, limite: int = 2) -> list[str]:
    """Agentes cujo papel mais combina com o pedido (BM25 sobre as notas dos agentes). É só sugestão para o maestro."""
    from .busca import Indice

    # Só o papel conta (o corpo das notas tem regras genéricas iguais para todos, que confundem o ranking).
    candidatos = {i: replace(n, corpo="") for i, n in agentes(ler_cofre(raiz)).items()
                  if i not in ("maestro", "secretario", "critico")}
    return [str(r.nota.meta.get("id", r.nota.nome)).lower() for r in Indice(candidatos).buscar(pedido, limite=limite)]


def rodar_turno(raiz: str | Path, agente: str, motivo: str, llm: LLM, max_passos: int = 12,
                lembretes: int = 1, pedido: str | None = None, contexto: str = "",
                indicados: list[str] | None = None, bloquear_recados: bool = False) -> ResultadoTurno:
    """Roda o turno. Se o modelo parar com recados ainda abertos, o motor lembra `lembretes` vez(es)."""
    raiz, agente = Path(raiz), agente.lower()
    bancada = Bancada(raiz, agente, pedido_padrao=pedido, indicados=list(indicados or []),
                      bloquear_recados=bloquear_recados)
    no_inicio = _abertos_meus(raiz, agente)
    mensagens = [
        {"role": "system", "content": instrucao_de_sistema(raiz, agente)},
        {"role": "user", "content": f"Você foi acordado: {motivo}.\n\nRecados abertos para você agora:\n\n{bancada.ler_mural()}"
                                    + (f"\n\n{contexto}" if contexto else "")},
    ]
    ferramentas = esquema_openai()
    resultado = ResultadoTurno(agente, "", 0)
    inicio = time.perf_counter()
    while resultado.passos < max_passos:
        resposta = llm.conversar(mensagens, ferramentas)
        resultado.passos += 1
        resultado.tokens_entrada += resposta.tokens_entrada
        resultado.tokens_saida += resposta.tokens_saida
        if not resposta.chamadas:
            pendentes = no_inicio & _abertos_meus(raiz, agente)
            if pendentes and lembretes > 0:
                lembretes -= 1
                resultado.lembretes += 1
                mensagens.append({"role": "assistant", "content": resposta.texto or ""})
                mensagens.append({"role": "user", "content": (
                    "Ainda estão abertos para você: " + "; ".join(sorted(pendentes)) + ". Antes de terminar, responda a "
                    "quem pediu com deixar_recado (responde = o nome do recado) e feche cada um com fechar_recado.")})
                continue
            resultado.resposta = resposta.texto.strip()
            break
        mensagens.append({"role": "assistant", "content": resposta.texto or "",
                          "tool_calls": [{"id": c.id, "type": "function",
                                          "function": {"name": c.nome, "arguments": json.dumps(c.argumentos, ensure_ascii=False)}}
                                         for c in resposta.chamadas]})
        for c in resposta.chamadas:
            _, saida = bancada.executar(c.nome, c.argumentos)
            mensagens.append({"role": "tool", "tool_call_id": c.id, "name": c.nome, "content": saida})
    else:
        resultado.parou_no_limite = True
        resultado.resposta = f"(parei no limite de {max_passos} passos)"
    resultado.registros = bancada.registros
    resultado.segundos = time.perf_counter() - inicio
    return resultado
