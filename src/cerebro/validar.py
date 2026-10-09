"""Checagens do cofre. Rodam no CI a cada commit: um agente que escreve errado quebra o build.

- links [[...]] que não apontam para nenhuma nota;
- recados sem os campos obrigatórios, com status inválido, ou endereçados a agente inexistente;
- agentes sem papel ou sem a lista do que podem escrever;
- dados que não podem estar num cofre público (CPF, cartão, chaves de API).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cofre import Nota, resolver
from .mural import HUMANO, STATUS, agentes, recados

_SENSIVEL = {
    "CPF": re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    "cartão": re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
    "chave de API": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b"),
}


@dataclass
class Problema:
    nota: str
    mensagem: str

    def __str__(self) -> str:
        return f"{self.nota}: {self.mensagem}"


def validar(notas: dict[str, Nota]) -> list[Problema]:
    problemas: list[Problema] = []
    ids = set(agentes(notas)) | {HUMANO, "todos"}

    for nota in notas.values():
        for alvo in nota.links:
            if resolver(notas, alvo) is None:
                problemas.append(Problema(str(nota.caminho), f"link quebrado [[{alvo}]]"))
        for nome, padrao in _SENSIVEL.items():
            if padrao.search(nota.corpo) or padrao.search(str(nota.meta)):
                problemas.append(Problema(str(nota.caminho), f"parece conter {nome}; o cofre é público"))

    for r in recados(notas):
        for campo in ("de", "para", "status", "criado", "assunto"):
            if not r.meta.get(campo):
                problemas.append(Problema(str(r.caminho), f"recado sem o campo '{campo}'"))
        if r.meta.get("status") and r.meta["status"] not in STATUS:
            problemas.append(Problema(str(r.caminho), f"status '{r.meta['status']}' inválido"))
        for campo in ("de", "para"):
            quem = str(r.meta.get(campo, "")).lower()
            if quem and quem not in ids:
                problemas.append(Problema(str(r.caminho), f"'{campo}: {quem}' não é um agente do cofre"))
        if r.meta.get("status") == "aberto" and str(r.meta.get("para", "")).lower() == HUMANO \
                and str(r.meta.get("de", "")).lower() != "maestro":
            problemas.append(Problema(str(r.caminho), f"só o maestro escreve para o {HUMANO}"))
        pai = str(r.meta.get("responde") or "").strip("[]")
        if pai and resolver(notas, pai) is None:
            problemas.append(Problema(str(r.caminho), f"responde a um recado que não existe: {pai}"))

    for id_, a in agentes(notas).items():
        for campo in ("papel", "escreve_em"):
            if not a.meta.get(campo):
                problemas.append(Problema(str(a.caminho), f"agente '{id_}' sem '{campo}'"))

    return problemas
