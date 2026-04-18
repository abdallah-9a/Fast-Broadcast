def register_and_get_token(
    client,
    username: str,
    email: str,
    password: str = "Password123",
):
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


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_create_room_requires_authentication(client):
    response = client.post(
        "/rooms",
        json={"name": "general", "visibility": "public"},
    )

    assert response.status_code == 401


def test_create_room_success(client):
    token = register_and_get_token(client, "room_owner", "room_owner@example.com")

    response = client.post(
        "/rooms",
        json={"name": "general", "visibility": "public"},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    room = response.json()
    assert room["id"] > 0
    assert room["name"] == "general"
    assert room["visibility"] == "public"
    assert room["is_active"] is True
    assert room["owner_user_id"] > 0


def test_list_rooms_respects_visibility_and_membership(client):
    owner_token = register_and_get_token(client, "private_owner", "private_owner@example.com")
    other_token = register_and_get_token(client, "public_owner", "public_owner@example.com")

    private_create = client.post(
        "/rooms",
        json={"name": "private-room", "visibility": "private"},
        headers=auth_headers(owner_token),
    )
    assert private_create.status_code == 201

    public_create = client.post(
        "/rooms",
        json={"name": "public-room", "visibility": "public"},
        headers=auth_headers(other_token),
    )
    assert public_create.status_code == 201

    owner_list = client.get("/rooms", headers=auth_headers(owner_token))
    assert owner_list.status_code == 200
    owner_names = {room["name"] for room in owner_list.json()}
    assert "private-room" in owner_names
    assert "public-room" in owner_names

    other_list = client.get("/rooms", headers=auth_headers(other_token))
    assert other_list.status_code == 200
    other_names = {room["name"] for room in other_list.json()}
    assert "public-room" in other_names
    assert "private-room" not in other_names


def test_get_room_details_enforces_private_access(client):
    owner_token = register_and_get_token(client, "room_owner2", "room_owner2@example.com")
    stranger_token = register_and_get_token(client, "stranger_user", "stranger_user@example.com")

    private_create = client.post(
        "/rooms",
        json={"name": "secret-room", "visibility": "private"},
        headers=auth_headers(owner_token),
    )
    assert private_create.status_code == 201
    private_room_id = private_create.json()["id"]

    owner_details = client.get(f"/rooms/{private_room_id}", headers=auth_headers(owner_token))
    assert owner_details.status_code == 200
    assert owner_details.json()["name"] == "secret-room"

    stranger_details = client.get(
        f"/rooms/{private_room_id}",
        headers=auth_headers(stranger_token),
    )
    assert stranger_details.status_code == 403
