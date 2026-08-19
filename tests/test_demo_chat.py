from fastapi.testclient import TestClient

from api.main import create_app


def test_demo_chat_route_serves_the_controlled_experience(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        response = client.get("/demo-chat")

    assert response.status_code == 200
    assert 'data-demo-chat="controlled"' in response.text


def test_demo_chat_matches_the_official_dangerous_contact_fixture(tmp_path) -> None:
    app = create_app(tmp_path / "guardian.db", tmp_path / "evidence")

    with TestClient(app) as client:
        response = client.get("/demo-chat")

    assert "Alex" in response.text
    assert "Você tem quantos anos?" in response.text
    assert "Qual é o nome da sua escola?" in response.text
    assert "Manda seu Instagram" in response.text
    assert "Manda uma foto sua" in response.text
