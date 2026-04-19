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


def create_room(client, token: str, name: str, visibility: str):
    response = client.post(
        "/rooms",
        json={"name": name, "visibility": visibility},
        headers=auth_headers(token),
    )
    assert response.status_code == 201
    return response.json()


def test_create_room_requires_authentication(client):
    response = client.post(
        "/rooms",
        json={"name": "general", "visibility": "public"},
    )

    assert response.status_code == 401


def test_create_room_success(client):
    token = register_and_get_token(client, "room_owner", "room_owner@example.com")

    response = client.post("/rooms", json={"name": "general", "visibility": "public"}, headers=auth_headers(token))

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

    create_room(client, owner_token, "private-room", "private")
    create_room(client, other_token, "public-room", "public")

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

    private_room_id = create_room(client, owner_token, "secret-room", "private")["id"]

    owner_details = client.get(f"/rooms/{private_room_id}", headers=auth_headers(owner_token))
    assert owner_details.status_code == 200
    assert owner_details.json()["name"] == "secret-room"

    stranger_details = client.get(
        f"/rooms/{private_room_id}",
        headers=auth_headers(stranger_token),
    )
    assert stranger_details.status_code == 403


def test_join_public_room_success_and_idempotent(client):
    owner_token = register_and_get_token(client, "owner_join", "owner_join@example.com")
    member_token = register_and_get_token(client, "member_join", "member_join@example.com")

    public_room = create_room(client, owner_token, "join-public-room", "public")
    room_id = public_room["id"]

    first_join = client.post(f"/rooms/{room_id}/join", headers=auth_headers(member_token))
    assert first_join.status_code == 200
    assert first_join.json()["room_id"] == room_id
    assert first_join.json()["role"] == "member"
    assert first_join.json()["left_at"] is None

    second_join = client.post(f"/rooms/{room_id}/join", headers=auth_headers(member_token))
    assert second_join.status_code == 200
    assert second_join.json()["id"] == first_join.json()["id"]


def test_join_private_room_forbidden_without_invite(client):
    owner_token = register_and_get_token(client, "private_owner_j", "private_owner_j@example.com")
    stranger_token = register_and_get_token(client, "private_stranger", "private_stranger@example.com")

    private_room = create_room(client, owner_token, "private-no-invite", "private")
    room_id = private_room["id"]

    join_response = client.post(f"/rooms/{room_id}/join", headers=auth_headers(stranger_token))
    assert join_response.status_code == 403


def test_leave_room_success_and_owner_cannot_leave(client):
    owner_token = register_and_get_token(client, "owner_leave", "owner_leave@example.com")
    member_token = register_and_get_token(client, "member_leave", "member_leave@example.com")

    public_room = create_room(client, owner_token, "leave-public-room", "public")
    room_id = public_room["id"]

    join_response = client.post(f"/rooms/{room_id}/join", headers=auth_headers(member_token))
    assert join_response.status_code == 200

    leave_response = client.post(f"/rooms/{room_id}/leave", headers=auth_headers(member_token))
    assert leave_response.status_code == 200
    assert leave_response.json()["left_at"] is not None

    owner_leave = client.post(f"/rooms/{room_id}/leave", headers=auth_headers(owner_token))
    assert owner_leave.status_code == 400


def test_list_room_members_private_access_control(client):
    owner_token = register_and_get_token(client, "members_owner", "members_owner@example.com")
    stranger_token = register_and_get_token(client, "members_stranger", "members_stranger@example.com")

    private_room = create_room(client, owner_token, "members-private-room", "private")
    room_id = private_room["id"]

    owner_members = client.get(f"/rooms/{room_id}/members", headers=auth_headers(owner_token))
    assert owner_members.status_code == 200
    assert len(owner_members.json()) == 1
    assert owner_members.json()[0]["role"] == "owner"

    stranger_members = client.get(f"/rooms/{room_id}/members", headers=auth_headers(stranger_token))
    assert stranger_members.status_code == 403
