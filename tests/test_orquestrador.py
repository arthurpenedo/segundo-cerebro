from pathlib import Path

from cerebro import cofre, mural, orquestrador

AGENTE = "---\ntipo: agente\nid: {id}\npapel: \"faz {id}\"\nescreve_em: [Mural]\n---\n# {id}\n"


def _cofre(tmp_path: Path) -> Path:
    (tmp_path / "Agentes").mkdir()
    for id_ in ("maestro", "dev", "critico", "secretario"):
        (tmp_path / "Agentes" / f"{id_}.md").write_text(AGENTE.format(id=id_), encoding="utf-8")
    (tmp_path / "00-Entrada").mkdir()
    (tmp_path / "00-Entrada" / "Pedido.md").write_text("---\ntipo: ideia\n---\n# Pedido\nFazer X.", encoding="utf-8")
    (tmp_path / "Mural").mkdir()
    (tmp_path / "Mural" / "Mural.md").write_text("---\ntipo: guia\n---\n# Mural", encoding="utf-8")
    (tmp_path / "Diario").mkdir()
    return tmp_path


def _fechar_meus(raiz: Path, agente: str) -> list[str]:
    nomes = []
    for r in mural.abertos_para(cofre.ler_cofre(raiz), agente):
        mural.mudar_status(raiz / r.caminho, "feito")
        nomes.append(r.nome)
    return nomes


def roteiro(raiz: Path):
    """Executor falso: maestro delega ao dev, dev pede revisão, crítico aprova, maestro leva ao arthur."""
    chamadas = []

    def executar(agente, instrucao, raiz_):
        chamadas.append(agente)
        meus = _fechar_meus(raiz_, agente)
        pai = meus[0] if meus else None
        if agente == "maestro" and not meus:
            mural.escrever_recado(raiz_, "maestro", "dev", "Fazer X", "Faça X.", pedido="Pedido")
            mural.escrever_recado(raiz_, "maestro", "arthur", "X em andamento", "Começamos.", pedido="Pedido")
        elif agente == "maestro":
            mural.escrever_recado(raiz_, "maestro", "arthur", "X pronto", "Aprovado, publique.", responde=pai)
        elif agente == "dev":
            mural.escrever_recado(raiz_, "dev", "critico", "Revisar X", "Pronto, revisa.", responde=pai)
        elif agente == "critico":
            mural.escrever_recado(raiz_, "critico", "maestro", "X aprovado", "Aprovado.", responde=pai)
        return f"{agente} ok"

    return executar, chamadas


def test_laco_acorda_cada_agente_ate_sobrar_so_decisao_humana(tmp_path):
    raiz = _cofre(tmp_path)
    executar, chamadas = roteiro(raiz)
    execucao = orquestrador.rodar(raiz, executar, aviso=lambda _: None)

    assert chamadas == ["maestro", "dev", "critico", "maestro", "secretario"]
    assert execucao.parou_por == orquestrador.CICLO_COMPLETO
    notas = cofre.ler_cofre(raiz)
    abertos = [r for r in mural.recados(notas) if r.meta["status"] == "aberto"]
    # recado humano não acorda ninguém, e do pedido só sobra o mais recente para o arthur
    assert [(r.meta["para"], r.meta["assunto"]) for r in abertos] == [("arthur", "X pronto")]
    assert all(r.meta.get("pedido") == "Pedido" for r in mural.recados(notas))  # herdado por --responde
    assert execucao.substituidos == 1
    assert "X pronto" in (raiz / "Caixa do Arthur.md").read_text(encoding="utf-8")
    registro = list((raiz / "Diario").glob("Execucao *.md"))
    assert len(registro) == 1 and "| 2 | dev |" in registro[0].read_text(encoding="utf-8")


def test_para_se_agente_nao_fecha_o_recado(tmp_path):
    raiz = _cofre(tmp_path)
    mural.escrever_recado(raiz, "maestro", "dev", "Fazer Y", "Faça Y.")
    chamadas = []
    execucao = orquestrador.rodar(raiz, lambda a, i, r: chamadas.append(a) or "", aviso=lambda _: None, diario=False)
    assert chamadas == ["dev"]
    assert "não fechou" in execucao.parou_por


def test_limite_de_turnos(tmp_path):
    raiz = _cofre(tmp_path)

    def pingue_pongue(agente, instrucao, raiz_):
        meus = _fechar_meus(raiz_, agente)
        outro = "critico" if agente != "critico" else "dev"
        mural.escrever_recado(raiz_, agente if agente != "maestro" else "maestro", outro, "De novo", "...",
                              responde=meus[0] if meus else None)
        return ""

    execucao = orquestrador.rodar(raiz, pingue_pongue, max_turnos=5, aviso=lambda _: None)
    assert len(execucao.turnos) == 5 and execucao.parou_por.startswith("limite")


def test_sem_nada_para_fazer_nao_registra(tmp_path):
    raiz = _cofre(tmp_path)
    (raiz / "00-Entrada" / "Pedido.md").unlink()
    execucao = orquestrador.rodar(raiz, lambda *a: "", aviso=lambda _: None)
    assert execucao.turnos == [] and not list((raiz / "Diario").glob("Execucao *.md"))


def test_entrada_e_marcada_encaminhada_e_nao_volta(tmp_path):
    raiz = _cofre(tmp_path)
    executar, chamadas = roteiro(raiz)
    orquestrador.rodar(raiz, executar, aviso=lambda _: None)
    assert "status: encaminhado" in (raiz / "00-Entrada" / "Pedido.md").read_text(encoding="utf-8")
    chamadas.clear()
    orquestrador.rodar(raiz, executar, aviso=lambda _: None)  # segunda rodada: nada novo
    assert chamadas == []


def test_marcar_cria_ou_troca_status(tmp_path):
    nota = tmp_path / "n.md"
    nota.write_text("# sem frontmatter", encoding="utf-8")
    orquestrador.marcar(nota, "encaminhado")
    assert nota.read_text(encoding="utf-8").startswith("---\nstatus: encaminhado\n---\n# sem")
    orquestrador.marcar(nota, "atendido")
    assert nota.read_text(encoding="utf-8").count("status:") == 1 and "status: atendido" in nota.read_text(encoding="utf-8")


def test_falha_nao_acorda_secretario_e_registra_respostas(tmp_path):
    raiz = _cofre(tmp_path)
    (raiz / "00-Entrada" / "Pedido.md").unlink()
    mural.escrever_recado(raiz, "maestro", "dev", "Fazer Y", "Faça Y.")
    chamadas = []
    orquestrador.rodar(raiz, lambda a, i, r: chamadas.append(a) or "Travei: sem permissão.", aviso=lambda _: None)
    assert chamadas == ["dev"]
    registro = next((raiz / "Diario").glob("Execucao *.md")).read_text(encoding="utf-8")
    assert "**1. dev:** Travei: sem permissão." in registro


def test_caixa_deixa_so_o_mais_recente_por_pedido(tmp_path):
    from datetime import datetime

    from cerebro import caixa

    raiz = _cofre(tmp_path)
    for hora, assunto, pedido in ((9, "A começou", "Pedido A"), (10, "B começou", "Pedido B"),
                                  (11, "A pronto", "Pedido A")):
        mural.escrever_recado(raiz, "maestro", "arthur", assunto, "...", pedido=pedido,
                              hoje=datetime(2026, 10, 9, hora))
    assert caixa.consolidar(raiz) == 1
    grupos = caixa.abertos_para_humano(cofre.ler_cofre(raiz))
    assert {p: [r.meta["assunto"] for r in lista] for p, lista in grupos.items()} == {"Pedido A": ["A pronto"], "Pedido B": ["B começou"]}
    antigo = next((raiz / "Mural").glob("*a-comecou.md")).read_text(encoding="utf-8")
    assert "status: substituido" in antigo and "Substituído por [[2026-10-09 maestro para arthur a-pronto]]" in antigo
    nota = caixa.gerar_nota(raiz).read_text(encoding="utf-8")
    assert nota.index("A pronto") < nota.index("B começou")  # pedido com novidade mais recente primeiro
