from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_uses_runtime_capabilities_instead_of_static_protection_claims() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "Proteção ativa</div>" not in html
    assert 'api("/capabilities")' in javascript
    assert "Demonstração local" in javascript
    assert "productCapabilities.real_screen_observation" in javascript


def test_ui_marks_unimplemented_observation_inputs_truthfully() -> None:
    javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "Captura da tela real — planejada" in javascript
    assert "OCR local — planejado" in javascript
    assert "Áudio do sistema — não implementado" in javascript
    assert "Áudio do sistema quando necessário" not in javascript
    assert "Microfone — não coletado" in javascript
    assert "Câmera — não coletada" in javascript
