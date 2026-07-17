"""Team isolation via API-key hash — memory keys never share across teams."""

from memory.store import MemoryStore
from gateway.auth_headers import get_team_id


def test_team_isolation_memory():
    store = MemoryStore()
    team_a = get_team_id("sk-ant-team-a-secret")
    team_b = get_team_id("sk-ant-team-b-secret")
    assert team_a != team_b

    store.write_project(
        workspace_id="ws1",
        topic="component:button",
        value={"name": "Button", "path": "ui/Button.tsx"},
        team_id=team_a,
    )

    found_a = store.read_project("ws1", "component:button", team_id=team_a)
    found_b = store.read_project("ws1", "component:button", team_id=team_b)

    assert found_a is not None
    assert found_a["name"] == "Button"
    assert found_b is None


def test_team_id_is_hash_not_key():
    key = "sk-ant-never-store-this"
    tid = get_team_id(key)
    assert key not in tid
    assert len(tid) == 16
