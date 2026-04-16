def create_user_and_token(client, username: str, email: str, password: str = "Password123"):
    register_response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert register_response.status_code == 201
    user_id = register_response.json()["id"]

    token_response = client.post(
        "/auth/token",
        data={"username": username, "password": password},
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    return user_id, token


def test_user_online_status_offline_by_default(client):
    user_id, _ = create_user_and_token(client, "presence_a", "presence_a@example.com")

    response = client.get(f"/users/{user_id}/online")

    assert response.status_code == 200
    assert response.json() == {"user_id": user_id, "is_online": False}


def test_user_online_status_changes_with_websocket_connection(client):
    user_id, token = create_user_and_token(client, "presence_b", "presence_b@example.com")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {token}"},
    ):
        online_response = client.get(f"/users/{user_id}/online")
        assert online_response.status_code == 200
        assert online_response.json() == {"user_id": user_id, "is_online": True}

    offline_response = client.get(f"/users/{user_id}/online")
    assert offline_response.status_code == 200
    assert offline_response.json() == {"user_id": user_id, "is_online": False}


def test_online_users_endpoint_returns_connected_users_only(client):
    user1_id, token1 = create_user_and_token(client, "presence_c", "presence_c@example.com")
    user2_id, _ = create_user_and_token(client, "presence_d", "presence_d@example.com")

    with client.websocket_connect(
        "/ws",
        headers={"Authorization": f"Bearer {token1}"},
    ):
        response = client.get("/online-users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == user1_id
        assert data[0]["username"] == "presence_c"
        assert data[0]["email"] == "presence_c@example.com"
        assert data[0]["is_active"] is True

        user2_status = client.get(f"/users/{user2_id}/online")
        assert user2_status.status_code == 200
        assert user2_status.json() == {"user_id": user2_id, "is_online": False}

    final_response = client.get("/online-users")
    assert final_response.status_code == 200
    assert final_response.json() == []
