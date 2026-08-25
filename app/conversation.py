"""Short-term, in-memory conversation state for follow-up questions.

Deliberately NOT a database table or vector store -- this is compact
structured context (active account/order/ticket/scenario + a capped list
of recent turns), not an unlimited transcript and not long-term memory.
Lost on process restart; a multi-process deployment would need this
replaced with a shared store (e.g. Redis), which is out of scope for a
single-process assessment deployment -- documented here rather than
silently assumed.

Scoped by (user_id, conversation_id) together, never conversation_id
alone: user_id always comes from the server-side authenticated lookup,
never trusted from the client beyond that, so a guessed/forged
conversation_id can never reach another user's conversation.
"""

import time
import uuid
from dataclasses import dataclass, field

_MAX_TURNS = 6  # last 3 user/assistant exchanges
_TITLE_MAX_LEN = 60


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    text: str


@dataclass
class ConversationState:
    conversation_id: str
    user_id: str
    turns: list = field(default_factory=list)  # list[ConversationTurn]
    active_account_id: str | None = None
    active_order_id: str | None = None
    active_ticket_id: str | None = None
    active_scenario: str | None = None
    recent_decision_summary: str | None = None
    pending_action: dict | None = None  # {action_id, action_type, account_id, ticket_id, order_id}
    # Set when gather_node asks a multi-account agent "which account is this
    # about?" -- lets the next turn deterministically resume active_scenario
    # if the reply is just a bare account confirmation ("yes, northstar"),
    # rather than trusting the planner to re-infer the scenario from a
    # confirmation reply that carries no topic information of its own.
    awaiting_account_clarification: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    title: str | None = None  # set from the first user turn, for the recent-conversations list
    _seq: int = 0  # ordering tie-breaker; wall-clock time.time() resolution is too coarse to order rapid turns


_STORE: dict[tuple, ConversationState] = {}
_seq_counter = 0


def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter


def get_or_create(user_id: str, conversation_id: str) -> ConversationState:
    key = (user_id, conversation_id)
    if key not in _STORE:
        _STORE[key] = ConversationState(conversation_id=conversation_id, user_id=user_id)
    return _STORE[key]


def get(user_id: str, conversation_id: str) -> ConversationState | None:
    # Strict lookup (never creates) so resuming a past conversation can't be
    # used to probe for the existence of another user's conversation_id --
    # scoped by the same (user_id, conversation_id) key as get_or_create.
    return _STORE.get((user_id, conversation_id))


def list_for_user(user_id: str) -> list[ConversationState]:
    convs = [c for (uid, _cid), c in _STORE.items() if uid == user_id]
    convs.sort(key=lambda c: c._seq, reverse=True)
    return convs


def append_turn(conv: ConversationState, role: str, text: str) -> None:
    conv.turns.append(ConversationTurn(role=role, text=text))
    if len(conv.turns) > _MAX_TURNS:
        conv.turns[:] = conv.turns[-_MAX_TURNS:]
    conv.updated_at = time.time()
    conv._seq = _next_seq()
    if conv.title is None and role == "user":
        conv.title = text if len(text) <= _TITLE_MAX_LEN else text[:_TITLE_MAX_LEN - 1] + "…"


def new_conversation_id() -> str:
    return uuid.uuid4().hex
