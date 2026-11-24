from datetime import datetime

from cerebro.atividade import atividade


def test_atividade_cria_ponto_ligado_ao_dia_e_as_fontes(tmp_path):
    quando = datetime(2026, 11, 24, 13, 5)
    nota, dia = atividade(tmp_path, "Leva Catho: 30 vagas", "ABC", ["Candidaturas", "vagas-locais.md"], quando)
    assert nota.name == "2026-11-24 13h05 Leva Catho 30 vagas.md"
    t = nota.read_text(encoding="utf-8")
    assert "[[2026-11-24]]" in t and "[[Candidaturas]]" in t and "[[vagas-locais]]" in t and "tipo: atividade" in t
    d = dia.read_text(encoding="utf-8")
    assert "## Atividades" in d and "[[2026-11-24 13h05 Leva Catho 30 vagas|Leva Catho: 30 vagas]]" in d


def test_segunda_atividade_reaproveita_secao_do_diario(tmp_path):
    (tmp_path / "Diario").mkdir()
    (tmp_path / "Diario" / "2026-11-24.md").write_text("# 24/11\n\ntexto antigo\n", encoding="utf-8")
    atividade(tmp_path, "A", quando=datetime(2026, 11, 24, 8, 0))
    atividade(tmp_path, "B", quando=datetime(2026, 11, 24, 9, 0))
    d = (tmp_path / "Diario" / "2026-11-24.md").read_text(encoding="utf-8")
    assert d.count("## Atividades") == 1 and "texto antigo" in d and d.index("|A]]") < d.index("|B]]")
