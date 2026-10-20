from datetime import date
from pathlib import Path

from cerebro import cofre, mural, painel, validar
from cerebro.cli import main

AGENTE = """---
tipo: agente
id: {id}
papel: "faz {id}"
escreve_em: [Mural]
---
# {id}
"""


def _cofre(tmp_path: Path) -> Path:
    for id_ in ("dev", "critico"):
        (tmp_path / "Agentes").mkdir(exist_ok=True)
        (tmp_path / "Agentes" / f"{id_}.md").write_text(AGENTE.format(id=id_), encoding="utf-8")
    (tmp_path / "Projetos").mkdir()
    (tmp_path / "Projetos" / "agente-banco.md").write_text("# agente-banco\nVer [[dev|o Dev]] e [[critico#Regras]].", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ignorado.md").write_text("[[nao-existe]]", encoding="utf-8")
    (tmp_path / "README.md").write_text("[[nao-existe]]", encoding="utf-8")
    return tmp_path


def test_le_notas_links_e_ignora_codigo(tmp_path):
    notas = cofre.ler_cofre(_cofre(tmp_path))
    assert set(notas) == {"dev", "critico", "agente-banco"}
    assert notas["agente-banco"].links == ["dev", "critico"]  # alias e seção removidos
    assert notas["dev"].tipo == "agente" and notas["dev"].pasta == "Agentes"
    assert validar.validar(notas) == []


def test_conversa_pelo_mural(tmp_path):
    raiz = _cofre(tmp_path)
    dia = date(2026, 10, 9)
    pedido = mural.escrever_recado(raiz, "dev", "critico", "Revisar números do post", "Confere o 49%?", hoje=dia)
    resposta = mural.escrever_recado(raiz, "critico", "dev", "Revisar números do post", "Aprovado.",
                                     responde=pedido.stem, hoje=dia)
    assert resposta.name.endswith("-2.md") or resposta.name != pedido.name

    notas = cofre.ler_cofre(raiz)
    assert [r.nome for r in mural.abertos_para(notas, "critico")] == [pedido.stem]
    mural.mudar_status(pedido, "feito")
    notas = cofre.ler_cofre(raiz)
    assert mural.abertos_para(notas, "critico") == []
    fios = mural.conversas(notas)
    assert len(fios) == 1 and [r.meta["de"] for r in fios[0]] == ["dev", "critico"]
    assert validar.validar(notas) == []


def test_validar_aponta_problemas(tmp_path):
    raiz = _cofre(tmp_path)
    (raiz / "Mural").mkdir()
    (raiz / "Mural" / "ruim.md").write_text(
        "---\ntipo: recado\nde: dev\npara: fantasma\nstatus: talvez\ncriado: 2026-10-09\n---\n"
        "Meu CPF é 123.456.789-09 e a chave sk-abcdefghijklmnopqrstuvwx. Ver [[sumiu]].", encoding="utf-8")
    mensagens = " | ".join(str(p) for p in validar.validar(cofre.ler_cofre(raiz)))
    for esperado in ("link quebrado [[sumiu]]", "CPF", "chave de API", "sem o campo 'assunto'",
                     "status 'talvez'", "'para: fantasma'"):
        assert esperado in mensagens


def test_painel_mostra_agentes_conversas_e_grafo(tmp_path):
    raiz = _cofre(tmp_path)
    mural.escrever_recado(raiz, "dev", "critico", "Revisão <urgente>", "Ver [[agente-banco]].", hoje=date(2026, 10, 9))
    pagina = painel.gerar(cofre.ler_cofre(raiz))
    assert "Revisão &lt;urgente&gt;" in pagina  # escapado
    assert "<span class='link'>agente-banco</span>" in pagina
    assert '"source": "agente-banco", "target": "dev"' in pagina


def test_cli_recado_mural_e_validar(tmp_path, capsys):
    raiz = _cofre(tmp_path)
    assert main(["--cofre", str(raiz), "recado", "--de", "dev", "--para", "critico", "--assunto", "Oi", "--texto", "Tudo certo?"]) == 0
    arquivo = capsys.readouterr().out.strip()
    assert arquivo.startswith("Mural/")
    main(["--cofre", str(raiz), "mural", "--para", "critico"])
    assert "[dev → critico] Oi" in capsys.readouterr().out
    assert main(["--cofre", str(raiz), "fechar", arquivo]) == 0
    assert main(["--cofre", str(raiz), "validar"]) == 0


def test_recado_com_texto_de_arquivo(tmp_path, capsys):
    raiz = _cofre(tmp_path)
    (raiz / ".rascunhos").mkdir()
    (raiz / ".rascunhos" / "r.txt").write_text("linha 1\n\"aspas\" e `crase`\nlinha 3", encoding="utf-8")
    assert main(["--cofre", str(raiz), "recado", "--de", "dev", "--para", "critico", "--assunto", "Longo",
                 "--texto-arquivo", ".rascunhos/r.txt"]) == 0
    arquivo = raiz / capsys.readouterr().out.strip()
    assert "\"aspas\" e `crase`\nlinha 3" in arquivo.read_text(encoding="utf-8")
    assert "r" not in cofre.ler_cofre(raiz)  # rascunho em pasta oculta não vira nota


def test_fechar_por_trecho_do_nome_e_nome_so_ascii(tmp_path, capsys):
    raiz = _cofre(tmp_path)
    a = mural.escrever_recado(raiz, "dev", "critico", "Revisar post", "x", hoje=date(2026, 10, 9))
    mural.escrever_recado(raiz, "dev", "critico", "Revisar README", "y", hoje=date(2026, 10, 9))
    assert a.name == "2026-10-09 dev para critico revisar-post.md" and a.name.isascii()
    assert main(["--cofre", str(raiz), "fechar", "revisar-post"]) == 0
    assert "status: feito" in a.read_text(encoding="utf-8")
    assert main(["--cofre", str(raiz), "fechar", "dev para critico"]) == 1  # ambíguo: não fecha nada
    assert "bate com 2 recados" in capsys.readouterr().out


def test_so_o_maestro_fala_com_o_arthur(tmp_path, capsys):
    raiz = _cofre(tmp_path)
    try:
        mural.escrever_recado(raiz, "dev", "arthur", "Pronto", "x")
        raise AssertionError("deveria recusar")
    except mural.RecadoRecusado as erro:
        assert "mande este recado para o maestro" in str(erro)
    assert not (raiz / "Mural").exists() or not list((raiz / "Mural").glob("*.md"))
    assert main(["--cofre", str(raiz), "recado", "--de", "dev", "--para", "arthur", "--assunto", "x", "--texto", "y"]) == 1
    assert "recado não escrito" in capsys.readouterr().out
    # escrito à mão, fora do comando: o validador pega
    (raiz / "Mural").mkdir(exist_ok=True)
    (raiz / "Mural" / "manual.md").write_text("---\ntipo: recado\nde: dev\npara: arthur\nstatus: aberto\n"
                                              "criado: 2026-10-09\nassunto: x\n---\nx", encoding="utf-8")
    assert any("só o maestro" in str(p) for p in validar.validar(cofre.ler_cofre(raiz)))


def test_pedido_e_herdado_pela_resposta(tmp_path):
    raiz = _cofre(tmp_path)
    a = mural.escrever_recado(raiz, "dev", "critico", "Revisar", "x", pedido="[[Post sobre algo]]")
    b = mural.escrever_recado(raiz, "critico", "dev", "Aprovado", "ok", responde=a.stem)
    notas = cofre.ler_cofre(raiz)
    assert notas[a.stem.lower()].meta["pedido"] == "Post sobre algo"
    assert notas[b.stem.lower()].meta["pedido"] == "Post sobre algo"
