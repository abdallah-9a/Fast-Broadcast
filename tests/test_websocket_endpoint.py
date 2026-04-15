import pytest
from starlette.websockets import WebSocketDisconnect


def create_user_and_token(client, username: str, email: str, password: str = "Password123"):
    register_response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert register_response.status_code == 201

    token_response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
    )
    assert token_response.status_code == 200
    return token_response.json()["access_token"]


def test_websocket_without_token_is_rejected(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_with_invalid_token_is_rejected(client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/ws",
            headers={"Authorization": "Bearer invalid.token.value"},
        ):
            pass

    assert exc_info.value.code == 1008


def test_websocket_with_valid_token_can_connect_and_send(client):
    token = create_user_and_token(client, username="wsuser", email="wsuser@example.com")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        websocket.send_text("hello from websocket test")
