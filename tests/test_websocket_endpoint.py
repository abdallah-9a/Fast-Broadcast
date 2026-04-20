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


def create_room(client, token: str, name: str, visibility: str = "public"):
    response = client.post(
        "/rooms",
        json={"name": name, "visibility": visibility},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()


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
        websocket.send_json(
            {
                "event": "room.message",
                "room_id": 0,
                "payload": {"message": "hello from websocket test"},
            }
        )


def test_websocket_room_message_requires_join_for_non_lobby_room(client):
    owner_token = create_user_and_token(client, username="wsowner", email="wsowner@example.com")
    user_token = create_user_and_token(client, username="wsmember", email="wsmember@example.com")
    room = create_room(client, owner_token, name="ws-public-room", visibility="public")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {user_token}"},
    ) as websocket:
        websocket.send_json(
            {
                "event": "room.message",
                "room_id": room["id"],
                "payload": {"message": "hello without join"},
            }
        )

        response = websocket.receive_json()
        assert response["event"] == "error"
        assert "Join room first" in response["payload"]["message"]


def test_websocket_join_private_room_requires_invite(client):
    owner_token = create_user_and_token(client, username="privateowner", email="privateowner@example.com")
    user_token = create_user_and_token(client, username="privateuser", email="privateuser@example.com")
    room = create_room(client, owner_token, name="ws-private-room", visibility="private")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {user_token}"},
    ) as websocket:
        websocket.send_json(
            {
                "event": "room.join",
                "room_id": room["id"],
                "payload": {},
            }
        )

        response = websocket.receive_json()
        assert response["event"] == "error"
        assert "Private room requires an invite" in response["payload"]["message"]


def test_websocket_returns_error_for_unsupported_event_type(client):
    token = create_user_and_token(client, username="wsuser2", email="wsuser2@example.com")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        websocket.send_json(
            {
                "event": "room.unknown",
                "room_id": 1,
                "payload": {},
            }
        )

        response = websocket.receive_json()
        assert response["event"] == "error"
        assert "Unsupported event type" in response["payload"]["message"]
