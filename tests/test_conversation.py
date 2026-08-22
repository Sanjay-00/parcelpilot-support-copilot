from app.conversation import append_turn, get, get_or_create, list_for_user, new_conversation_id


def test_get_or_create_returns_same_state_for_same_key():
    cid = new_conversation_id()
    first = get_or_create("priya_mehta", cid)
    first.active_account_id = "ACCT-001"
    second = get_or_create("priya_mehta", cid)
    assert second is first
    assert second.active_account_id == "ACCT-001"


def test_different_users_cannot_share_conversation_even_with_same_conversation_id():
    cid = new_conversation_id()
    priya_state = get_or_create("priya_mehta", cid)
    priya_state.active_account_id = "ACCT-001"

    arjun_state = get_or_create("arjun_rao", cid)  # same conversation_id, different user
    assert arjun_state is not priya_state
    assert arjun_state.active_account_id is None


def test_append_turn_caps_at_max_turns():
    cid = new_conversation_id()
    conv = get_or_create("neha_kapoor", cid)
    for i in range(10):
        append_turn(conv, "user", f"message {i}")
    assert len(conv.turns) == 6
    assert conv.turns[-1].text == "message 9"
    assert conv.turns[0].text == "message 4"


def test_get_returns_none_for_a_conversation_that_does_not_exist_for_this_user():
    cid = new_conversation_id()
    get_or_create("priya_mehta", cid)  # exists for priya_mehta
    assert get("arjun_rao", cid) is None  # but not for a different user
    assert get("priya_mehta", cid) is not None


def test_list_for_user_only_returns_that_users_conversations_most_recent_first():
    user = f"user-{new_conversation_id()}"  # unique per test run, isolated from other tests' state
    older = get_or_create(user, new_conversation_id())
    append_turn(older, "user", "first question")
    newer = get_or_create(user, new_conversation_id())
    append_turn(newer, "user", "second question")
    other_user_conv = get_or_create(f"other-{user}", new_conversation_id())
    append_turn(other_user_conv, "user", "not this user's conversation")

    listed = list_for_user(user)
    assert [c.conversation_id for c in listed] == [newer.conversation_id, older.conversation_id]


def test_title_is_set_from_first_user_turn_and_does_not_change_after():
    conv = get_or_create("neha_kapoor", new_conversation_id())
    append_turn(conv, "user", "What are Northstar's cancellation fees?")
    append_turn(conv, "assistant", "Some answer.")
    append_turn(conv, "user", "A different follow-up question")
    assert conv.title == "What are Northstar's cancellation fees?"
