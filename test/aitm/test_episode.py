"""Episode correlation: session+task keyed, no collapse across tasks."""
import os
import tempfile

from mitmproxy.aitm.daemon import Daemon

def _obs(i, session, task=None):
    return {"id": f"obs_{i}", "source": "http", "timestamp": 1700000000000 + i,
        "sessionId": session, "taskId": task, "priority": "interesting",
        "metadata": {"method": "GET", "host": "app.example", "path": f"/p{i}", "status": 200}}

def test_same_session_different_tasks_separate_episodes():
    tmp = tempfile.mkdtemp()
    d = Daemon(db=os.path.join(tmp, "a.db"), sock=os.path.join(tmp, "a.sock"))
    d.start()
    try:
        d.pipeline.ingest(_obs(1, "sess_x", "task_a"))
        d.pipeline.ingest(_obs(2, "sess_x", "task_a"))
        d.pipeline.ingest(_obs(3, "sess_x", "task_b"))
        d.pipeline.flush_episodes()
        rows = d.store.fetch(
            "SELECT session, task, obs FROM episodes ORDER BY rowid", ())
        by_task = {r[1]: r[2] for r in rows}
        assert by_task == {"task_a": 2, "task_b": 1}, rows
    finally:
        d.stop()

def test_session_without_task_gets_episode():
    tmp = tempfile.mkdtemp()
    d = Daemon(db=os.path.join(tmp, "a.db"), sock=os.path.join(tmp, "a.sock"))
    d.start()
    try:
        d.pipeline.ingest(_obs(1, "sess_y"))
        d.pipeline.flush_episodes()
        rows = d.store.fetch("SELECT session, task, obs FROM episodes", ())
        assert rows == [("sess_y", None, 1)], rows
    finally:
        d.stop()

def test_taskless_obs_does_not_join_tasked_episode():
    tmp = tempfile.mkdtemp()
    d = Daemon(db=os.path.join(tmp, "a.db"), sock=os.path.join(tmp, "a.sock"))
    d.start()
    try:
        d.pipeline.ingest(_obs(1, "sess_z", "task_a"))
        d.pipeline.ingest(_obs(2, "sess_z"))
        d.pipeline.flush_episodes()
        rows = d.store.fetch(
            "SELECT session, task, obs FROM episodes ORDER BY rowid", ())
        assert len(rows) == 2 and {r[1] for r in rows} == {"task_a", None}, rows
    finally:
        d.stop()
