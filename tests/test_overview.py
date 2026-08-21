from app.auth import get_user, load as load_users
from app.documents import load as load_docs
from app.overview import issue_clusters
from app.seed_accounts_orders_tickets import load as load_base
from app.config import DATA_PACK_XLSX


def test_ki208_cluster_includes_tkt502(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_docs(conn)
    load_users(conn)
    manager = get_user(conn, "manager")
    clusters = issue_clusters(conn, manager)
    ki208 = next(c for c in clusters if c["ki_id"] == "product_guide_ki208")
    assert "TKT-502" in ki208["ticket_ids"]


import os

import pytest

from app.overview import sla_risk_tickets


@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="requires GEMINI_API_KEY")
def test_tkt501_and_tkt505_are_p1_at_risk(conn):
    load_base(conn, DATA_PACK_XLSX)
    load_docs(conn)
    load_users(conn)
    manager = get_user(conn, "manager")
    results = {r["ticket_id"]: r for r in sla_risk_tickets(conn, manager)}
    assert results["TKT-501"]["severity"] == "P1"
    assert results["TKT-505"]["severity"] == "P1"
