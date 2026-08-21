from app.documents import load


def test_document_chunks_loaded_with_correct_scoping(conn):
    load(conn)
    total = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
    assert total == 19

    deprecated = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE status = 'DEPRECATED'"
    ).fetchone()[0]
    assert deprecated == 1

    northstar_scoped = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE customer_id = 'ACCT-001'"
    ).fetchone()[0]
    assert northstar_scoped == 4

    global_chunks = conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE customer_id IS NULL"
    ).fetchone()[0]
    assert global_chunks == 12

    ki208 = conn.execute(
        "SELECT text FROM document_chunks WHERE chunk_id = 'product_guide_ki208'"
    ).fetchone()
    assert "3,000 rows" in ki208["text"]
