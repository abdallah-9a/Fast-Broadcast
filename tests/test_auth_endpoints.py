def register_user(
    client,
    username: str = "alice",
    email: str = "alice@example.com",
    password: str = "Password123",
):
    return client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )


def test_register_success_returns_public_user_data(client):
    response = register_user(client)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] > 0
    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert data["is_active"] is True
    assert "hashed_password" not in data


def test_register_duplicate_user_returns_400(client):
    first = register_user(client)
    assert first.status_code == 201

    second = register_user(client)
    assert second.status_code == 400
    assert second.json()["detail"] == "User with this email or username already exists."


def test_token_success_returns_bearer_token(client):
    created = register_user(client, username="bob", email="bob@example.com")
    assert created.status_code == 201

    token_response = client.post(
        "/auth/token",
        data={"username": "bob", "password": "Password123"},
    )

    assert token_response.status_code == 200
    payload = token_response.json()
    assert payload["token_type"] == "bearer"
    assert isinstance(payload["access_token"], str)
    assert payload["access_token"]


def test_token_invalid_credentials_returns_401(client):
    created = register_user(client, username="carol", email="carol@example.com")
    assert created.status_code == 201

    token_response = client.post(
        "/auth/token",
        data={"username": "carol", "password": "WrongPassword"},
    )

    assert token_response.status_code == 401
    assert token_response.json()["detail"] == "Incorrect username or password"
