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
from dataclasses import dataclass, field
from pathlib import Path

from .cofre import ler_cofre
from .ferramentas import Bancada, Registro, esquema_openai
from .llm import LLM
from .mural import HUMANO, agentes

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

    @property
    def recusas(self) -> int:
        return sum(not r.ok for r in self.registros)


def instrucao_de_sistema(raiz: Path, agente: str) -> str:
    ficha = agentes(ler_cofre(raiz)).get(agente)
    if ficha is None:
        raise ValueError(f"'{agente}' não é um agente do cofre")
    pastas = ", ".join(str(p) for p in ficha.meta.get("escreve_em") or [])
    return (f"{REGRAS}\n\nVocê é o agente `{agente}` ({ficha.meta.get('nome', agente)}). Pode escrever em: {pastas}.\n"
            f"Sua nota no cofre (papel e regras):\n\n{ficha.corpo.strip()}")


def rodar_turno(raiz: str | Path, agente: str, motivo: str, llm: LLM, max_passos: int = 12) -> ResultadoTurno:
    raiz, agente = Path(raiz), agente.lower()
    bancada = Bancada(raiz, agente)
    mensagens = [
        {"role": "system", "content": instrucao_de_sistema(raiz, agente)},
        {"role": "user", "content": f"Você foi acordado: {motivo}.\n\nRecados abertos para você agora:\n\n{bancada.ler_mural()}"},
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
