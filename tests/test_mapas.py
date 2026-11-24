from cerebro.mapas import gerar_mapas


def test_mapas_ligam_cada_pasta_e_entram_no_inicio(tmp_path):
    (tmp_path / "Diario").mkdir()
    (tmp_path / "Diario" / "2026-11-23.md").write_text("x", encoding="utf-8")
    (tmp_path / "Diario" / "2026-11-24.md").write_text("x", encoding="utf-8")
    (tmp_path / "Ideias").mkdir()
    (tmp_path / "Ideias" / "Jogo.md").write_text("x", encoding="utf-8")
    (tmp_path / "Tarefas.md").write_text("x", encoding="utf-8")
    (tmp_path / "Inicio.md").write_text("# Inicio\n\n## Mapas\n- [[Mapa - Velho]]\n\n## Outra\nfica\n", encoding="utf-8")
    (tmp_path / "Mapas").mkdir()
    (tmp_path / "Mapas" / "Mapa - Velho.md").write_text("x", encoding="utf-8")
    feitos = gerar_mapas(tmp_path)
    assert sorted(p.stem for p in feitos) == ["Mapa - Diario", "Mapa - Ideias", "Mapa - Raiz"]
    diario = (tmp_path / "Mapas" / "Mapa - Diario.md").read_text(encoding="utf-8")
    assert diario.index("[[2026-11-24]]") < diario.index("[[2026-11-23]]") and "[[Inicio]]" in diario
    assert "[[Tarefas]]" in (tmp_path / "Mapas" / "Mapa - Raiz.md").read_text(encoding="utf-8")
    ini = (tmp_path / "Inicio.md").read_text(encoding="utf-8")
    assert ini.count("## Mapas") == 1 and "[[Mapa - Ideias]]" in ini and "Velho" not in ini and "fica" in ini
    assert not (tmp_path / "Mapas" / "Mapa - Velho.md").exists()
    gerar_mapas(tmp_path)
    assert (tmp_path / "Inicio.md").read_text(encoding="utf-8").count("## Mapas") == 1


def test_ligar_soltas_poe_rodape_uma_vez_e_respeita_quem_ja_tem_link(tmp_path):
    from cerebro.mapas import ligar_soltas
    (tmp_path / "Diario").mkdir()
    for d in ("2026-11-22", "2026-11-23", "2026-11-24"):
        (tmp_path / "Diario" / f"{d}.md").write_text("texto", encoding="utf-8")
    (tmp_path / "Aprendizados").mkdir()
    (tmp_path / "Aprendizados" / "Aprendizados 2026-11-23.md").write_text("x", encoding="utf-8")
    (tmp_path / "Ideias").mkdir()
    (tmp_path / "Ideias" / "Ligada.md").write_text("ver [[Outra]]", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("regras", encoding="utf-8")
    feitas = ligar_soltas(tmp_path)
    assert len(feitas) == 4
    meio = (tmp_path / "Diario" / "2026-11-23.md").read_text(encoding="utf-8")
    assert "[[Mapa - Diario]]" in meio and "anterior: [[2026-11-22]]" in meio and "seguinte: [[2026-11-24]]" in meio
    assert "dia: [[2026-11-23]]" in (tmp_path / "Aprendizados" / "Aprendizados 2026-11-23.md").read_text(encoding="utf-8")
    assert (tmp_path / "Ideias" / "Ligada.md").read_text(encoding="utf-8") == "ver [[Outra]]"
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "regras"
    assert ligar_soltas(tmp_path) == []
