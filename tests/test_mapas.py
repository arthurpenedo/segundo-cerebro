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
