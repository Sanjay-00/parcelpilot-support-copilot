import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app import db


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_schema(connection)
    yield connection
    connection.close()
