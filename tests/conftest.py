import os
import tempfile
from pathlib import Path
import pytest
from ulum.db.database import init_db
from ulum.db.repository import Repository

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = init_db(path)
    repo = Repository(conn)
    yield repo, path
    conn.close()
    if os.path.exists(path):
        os.remove(path)
