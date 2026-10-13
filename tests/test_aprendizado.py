from datetime import datetime

from cerebro.aprendizado import aprendi


def test_registra_no_dia_e_no_manual(tmp_path):
    quando = datetime(2026, 10, 13, 9, 30)
    aprendi(tmp_path, "push   travou;  usar o gh", "Publicar no GitHub", quando)
    aprendi(tmp_path, "segunda lição", None, quando)
    dia = (tmp_path / "Aprendizados" / "2026-10-13.md").read_text(encoding="utf-8")
    assert "- 09:30 [[Publicar no GitHub]] · push travou; usar o gh" in dia and "- 09:30 segunda lição" in dia
    manual = (tmp_path / "Manual" / "Publicar no GitHub.md").read_text(encoding="utf-8")
    assert "- push travou; usar o gh ([[2026-10-13]])" in manual
