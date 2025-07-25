"""Tests the xonsh history."""

# pylint: disable=protected-access
import itertools
import os
import shlex
import sys
import time

import pytest

from xonsh.history.main import history_main
from xonsh.history.sqlite import SqliteHistory, _xh_sqlite_get_conn
from xonsh.platform import ON_WINDOWS

hist_file_count = itertools.count(0)

skipwin311 = pytest.mark.skipif(
    ON_WINDOWS and sys.version_info > (3, 10),
    reason="obnoxious regression in sqlite file closing behavior",
)


@pytest.fixture
def hist(tmpdir):
    h = SqliteHistory(
        filename=tmpdir / f"xonsh-HISTORY-TEST{next(hist_file_count)}.sqlite",
        sessionid=str(tmpdir / "SESSIONID"),
        gc=False,
    )
    yield h


def _clean_up(h):
    conn = _xh_sqlite_get_conn(h.filename)
    conn.close()
    filename = h.filename
    del h
    os.remove(filename)


@skipwin311
def test_hist_append(hist, xession):
    """Verify appending to the history works."""
    xession.env["HISTCONTROL"] = set()
    hf = hist.append({"inp": "still alive", "rtn": 1})
    assert hf is None
    items = list(hist.items())
    assert len(items) == 1
    assert "still alive" == items[0]["inp"]
    assert 1 == items[0]["rtn"]
    hist.append({"inp": "still alive", "rtn": 0})
    items = list(hist.items())
    assert len(items) == 2
    assert "still alive" == items[1]["inp"]
    assert 0 == items[1]["rtn"]
    assert list(hist.all_items()) == items
    _clean_up(hist)


@skipwin311
def test_hist_attrs(hist, xession):
    xession.env["HISTCONTROL"] = set()
    hf = hist.append({"inp": "ls foo", "rtn": 1})
    assert hf is None
    assert "ls foo" == hist.inps[0]
    assert "ls foo" == hist.inps[-1]
    assert 1 == hist.rtns[0]
    assert 1 == hist.rtns[-1]
    assert None is hist.outs[-1]
    assert [1] == hist.rtns[:]
    hist.append({"inp": "ls bar", "rtn": 0})
    assert "ls bar" == hist.inps[1]
    assert "ls bar" == hist.inps[-1]
    assert 0 == hist.rtns[1]
    assert 0 == hist.rtns[-1]
    assert None is hist.outs[-1]
    assert [1, 0] == hist.rtns[:]
    assert len(hist.tss) == 2
    assert len(hist.tss[0]) == 2

    _clean_up(hist)


CMDS = ["ls", "cat hello kitty", "abc", "def", "touch me", "grep from me"]


@skipwin311
@pytest.mark.parametrize(
    "inp, commands, offset",
    [
        ("", CMDS, (0, 1)),
        ("-r", list(reversed(CMDS)), (len(CMDS) - 1, -1)),
        ("0", CMDS[0:1], (0, 1)),
        ("1", CMDS[1:2], (1, 1)),
        ("-2", CMDS[-2:-1], (len(CMDS) - 2, 1)),
        ("1:3", CMDS[1:3], (1, 1)),
        ("1::2", CMDS[1::2], (1, 2)),
        ("-4:-2", CMDS[-4:-2], (len(CMDS) - 4, 1)),
    ],
)
def test_show_cmd_numerate(inp, commands, offset, hist, xession, capsys):
    """Verify that CLI history commands work."""
    base_idx, step = offset
    xession.history = hist
    xession.env["HISTCONTROL"] = set()
    for ts, cmd in enumerate(CMDS):  # populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})

    exp = (f"{base_idx + idx * step}: {cmd}" for idx, cmd in enumerate(list(commands)))
    exp = "\n".join(exp)

    history_main(["show", "-n"] + shlex.split(inp))
    out, err = capsys.readouterr()
    assert out.rstrip() == exp

    _clean_up(hist)


@skipwin311
def test_histcontrol(hist, xession):
    """Test HISTCONTROL=ignoredups,ignoreerr"""

    ignore_opts = ",".join(["ignoredups", "ignoreerr", "ignorespace"])
    xession.env["HISTCONTROL"] = ignore_opts
    assert len(hist) == 0

    # An error, items() remains empty
    hist.append({"inp": "ls foo", "rtn": 2})
    assert len(hist) == 0
    assert len(hist.inps) == 1
    assert len(hist.rtns) == 1
    assert 2 == hist.rtns[-1]

    # Success
    hist.append({"inp": "ls foobazz", "rtn": 0})
    assert len(hist) == 1
    assert len(hist.inps) == 2
    assert len(hist.rtns) == 2
    items = list(hist.items())
    assert "ls foobazz" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    # Error
    hist.append({"inp": "ls foo", "rtn": 2})
    assert len(hist) == 1
    items = list(hist.items())
    assert "ls foobazz" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 2 == hist.rtns[-1]

    # File now exists, success
    hist.append({"inp": "ls foo", "rtn": 0})
    assert len(hist) == 2
    items = list(hist.items())
    assert "ls foo" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    # Success
    hist.append({"inp": "ls", "rtn": 0})
    assert len(hist) == 3
    items = list(hist.items())
    assert "ls" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    # Dup
    hist.append({"inp": "ls", "rtn": 0})
    assert len(hist) == 3

    # Success
    hist.append({"inp": "/bin/ls", "rtn": 0})
    assert len(hist) == 4
    items = list(hist.items())
    assert "/bin/ls" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    # Error
    hist.append({"inp": "ls bazz", "rtn": 1})
    assert len(hist) == 4
    items = list(hist.items())
    assert "/bin/ls" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert "ls bazz" == hist.inps[-1]
    assert 1 == hist.rtns[-1]

    # Error
    hist.append({"inp": "ls bazz", "rtn": -1})
    assert len(hist) == 4
    items = list(hist.items())
    assert "/bin/ls" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert -1 == hist.rtns[-1]

    # Success
    hist.append({"inp": "echo not secret", "rtn": 0, "spc": False})
    assert len(hist) == 5
    items = list(hist.items())
    assert "echo not secret" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    # Space
    hist.append({"inp": "echo secret command", "rtn": 0, "spc": True})
    assert len(hist) == 5
    items = list(hist.items())
    assert "echo not secret" == items[-1]["inp"]
    assert 0 == items[-1]["rtn"]
    assert 0 == hist.rtns[-1]

    _clean_up(hist)


@skipwin311
def test_histcontrol_erase_dup(hist, xession):
    """Test HISTCONTROL=erasedups"""

    xession.env["HISTCONTROL"] = "erasedups"
    assert len(hist) == 0

    hist.append({"inp": "ls foo", "rtn": 2})
    hist.append({"inp": "ls foobazz", "rtn": 0})
    hist.append({"inp": "ls foo", "rtn": 0})
    hist.append({"inp": "ls foobazz", "rtn": 0})
    hist.append({"inp": "ls foo", "rtn": 0})
    assert len(hist) == 2
    assert len(hist.inps) == 5

    items = list(hist.items())
    assert "ls foo" == items[-1]["inp"]
    assert "ls foobazz" == items[-2]["inp"]
    assert items[-2]["frequency"] == 2
    assert items[-1]["frequency"] == 3

    _clean_up(hist)


@skipwin311
@pytest.mark.parametrize(
    "index, exp",
    [
        (-1, ("grep from me", "out", 0, (5, 6))),
        (1, ("cat hello kitty", "out", 0, (1, 2))),
        (
            slice(1, 3),
            [("cat hello kitty", "out", 0, (1, 2)), ("abc", "out", 0, (2, 3))],
        ),
    ],
)
def test_history_getitem(index, exp, hist, xession):
    xession.env["HISTCONTROL"] = set()
    xession.env["XONSH_STORE_STDOUT"] = True
    attrs = ("inp", "out", "rtn", "ts")

    for ts, cmd in enumerate(CMDS):  # populate the shell history
        entry = {
            k: v for k, v in zip(attrs, [cmd, "out", 0, (ts, ts + 1)], strict=False)
        }
        hist.append(entry)

    entry = hist[index]
    if isinstance(entry, list):
        assert [(e.cmd, e.out, e.rtn, e.ts) for e in entry] == exp
    else:
        assert (entry.cmd, entry.out, entry.rtn, entry.ts) == exp

    _clean_up(hist)


@skipwin311
def test_hist_clear_cmd(hist, xession, capsys, tmpdir):
    """Verify that the CLI history clear command works."""
    xession.env.update({"XONSH_DATA_DIR": str(tmpdir)})
    xession.history = hist
    xession.env["HISTCONTROL"] = set()

    for ts, cmd in enumerate(CMDS):  # populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})
    assert len(xession.history) == 6

    history_main(["clear"])

    out, err = capsys.readouterr()
    assert err.rstrip() == "History cleared"
    assert len(xession.history) == 0

    _clean_up(hist)


@skipwin311
def test_hist_off_cmd(hist, xession, capsys, tmpdir):
    """Verify that the CLI history off command works."""
    xession.env.update({"XONSH_DATA_DIR": str(tmpdir)})
    xession.history = hist
    xession.env["HISTCONTROL"] = set()

    for ts, cmd in enumerate(CMDS):  # populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})
    assert len(xession.history) == 6

    history_main(["off"])

    out, err = capsys.readouterr()
    assert err.rstrip() == "History off"
    assert len(xession.history) == 0

    for ts, cmd in enumerate(CMDS):  # attempt to populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})

    assert len(xession.history) == 0

    _clean_up(hist)


@skipwin311
def test_hist_on_cmd(hist, xession, capsys, tmpdir):
    """Verify that the CLI history on command works."""
    xession.env.update({"XONSH_DATA_DIR": str(tmpdir)})
    xession.history = hist
    xession.env["HISTCONTROL"] = set()

    for ts, cmd in enumerate(CMDS):  # populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})
    assert len(xession.history) == 6

    history_main(["off"])
    history_main(["on"])

    out, err = capsys.readouterr()
    assert err.rstrip().endswith("History on")
    assert len(xession.history) == 0

    for ts, cmd in enumerate(CMDS):  # populate the shell history
        hist.append({"inp": cmd, "rtn": 0, "ts": (ts + 1, ts + 1.5)})

    assert len(xession.history) == 6

    _clean_up(hist)


@skipwin311
def test_hist_store_cwd(hist, xession):
    hist.save_cwd = True
    hist.append({"inp": "# saving with cwd", "rtn": 0, "out": "yes", "cwd": "/tmp"})
    hist.save_cwd = False
    hist.append({"inp": "# saving without cwd", "rtn": 0, "out": "yes", "cwd": "/tmp"})

    cmds = [i for i in hist.all_items()]
    assert cmds[0]["cwd"] == "/tmp"
    assert cmds[1]["cwd"] is None

    _clean_up(hist)


@pytest.mark.parametrize(
    "src_sessionid", [None, "e2265764-041c-4c57-acba-49d4e4f676e5"]
)
def test_hist_pull(src_sessionid, tmpdir, ptk_shell, monkeypatch):
    """Test that `pull` method correctly loads history entries
    added to the database by other sessions."""
    db_file = tmpdir / "xonsh-HISTORY-TEST-PULL.sqlite"
    before = time.time()

    # simulate commands being run in other sessions before this session starts
    hist_a = SqliteHistory(filename=db_file, gc=False, sessionid=src_sessionid)
    hist_a.append({"inp": "cmd hist_a before", "rtn": 0, "ts": [before, before]})
    hist_b = SqliteHistory(filename=db_file, gc=False)
    hist_b.append({"inp": "cmd hist_b after", "rtn": 0, "ts": [before, before]})

    hist_main = SqliteHistory(filename=db_file, gc=False)
    # simulate commands being run in other sessions after this session starts
    after = time.time() + 1
    hist_a.append({"inp": "cmd hist_a after", "rtn": 0, "ts": [after, after]})
    hist_b.append({"inp": "cmd hist_b after", "rtn": 0, "ts": [after + 1, after + 1]})

    # pull only works with PTK shell
    monkeypatch.setattr("xonsh.built_ins.XSH.shell.shell", ptk_shell[2])
    hist_main.pull(src_sessionid=src_sessionid)
    hist_strings = ptk_shell[2].prompter.history.get_strings()

    if src_sessionid is None:
        # ensure that only commands from after the pulling session started get pulled in
        assert hist_strings == ["cmd hist_a after", "cmd hist_b after"]
    else:
        # and that the commands are correctly filtered by session id if applicable
        assert hist_strings == ["cmd hist_a after"]


def test_hist_pull_mixed(ptk_shell, tmpdir, xonsh_session, monkeypatch):
    """Test that mixing general pull with session-specific pull
    does not result in missed or duplicate items.
    """
    monkeypatch.setattr(xonsh_session.shell, "shell", ptk_shell[2])

    # make sure that all of our fake commands have real, sequential timestamps
    def cmd(inp):
        start, end = time.time(), time.time()
        return {"inp": inp, "rtn": 0, "ts": [start, end]}

    db_file = tmpdir / "xonsh-HISTORY-TEST-PULL-MIXED.sqlite"
    hist_a = SqliteHistory(filename=db_file, gc=False)
    hist_b = SqliteHistory(filename=db_file, gc=False)
    hist_main = SqliteHistory(filename=db_file, gc=False)

    # windows time.time() has only ~16ms granularity, so give it a chance to increment here
    time.sleep(0.032)
    hist_a.append(cmd("a1"))
    hist_b.append(cmd("b1"))
    hist_main.pull(src_sessionid=str(hist_a.sessionid))
    # at this point, hist_main will only have "a1" in its history
    assert ptk_shell[2].prompter.history.get_strings() == ["a1"]

    time.sleep(0.032)
    hist_a.append(cmd("a2"))
    hist_b.append(cmd("b2"))
    hist_main.pull()
    # hist_main should now have all the items we just added

    hist_strings = ptk_shell[2].prompter.history.get_strings()
    assert hist_strings == ["a1", "b1", "a2", "b2"]
