from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_uses_runtime_capabilities_instead_of_static_protection_claims() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "Proteção ativa</div>" not in html
    assert 'api("/capabilities")' in javascript
    assert "Dados simulados" in javascript
    assert "productCapabilities.real_screen_observation" in javascript


def test_ui_marks_unimplemented_observation_inputs_truthfully() -> None:
    javascript = (ROOT / "web" / "static" / "app.js").read_text(encoding="utf-8")

    assert "Tela do dispositivo — não acessada" in javascript
    assert "Texto de outros aplicativos — não acessado" in javascript
    assert "Áudio do sistema — não acessado" in javascript
    assert "Microfone — não acessado" in javascript
    assert "Câmera — não acessada" in javascript


def test_ui_avoids_project_pitch_and_presenter_language() -> None:
    visible_sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "web/index.html",
            "web/static/app.js",
            "web/demo-chat.html",
            "web/static/demo-chat.js",
        )
    )

    for forbidden_copy in (
        "Arquitetura preparada",
        "Visualização em tempo real",
        "Demo atual",
        "Fixtures e telemetria",
        "próxima etapa",
        "CONTROLE DO APRESENTADOR",
        "Pronta para captura",
    ):
        assert forbidden_copy not in visible_sources

    assert "Conversa simulada" in visible_sources
    assert "nenhuma tela real está sendo observada" in visible_sources
