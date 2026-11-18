"""Background downloads of weights: one detached worker process per set, its state in a small JSON file.

The host runs one process per tool run and kills it when the user presses another control, so a download cannot live
in the tool's own process. ``start`` launches ``python autoseg_jobs.py …`` in a new session (Unix) or process group
(Windows): the host kills only its direct child, so the worker survives clicks and the window closing. It stops when
radspider exits (it watches radspider's process), when ``stop`` asks it to, or when the download ends.

State file ``<jobs>/<key>.json``: ``{"pid", "fraction", "error"}``; absent = no job. The worker removes it on success
and on a stop; it keeps it with ``error`` set on a failure, so the window can show why.
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

POLL = 0.5  # seconds between two looks at a state file


def jobs_dir():
    d = os.environ.get("RADSPIDER_AUTOSEG_JOBS") or os.path.join(os.path.expanduser("~"), ".cache", "radspider",
                                                                   "auto-segmentation-jobs")
    os.makedirs(d, exist_ok=True)
    return d


def key(label):
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _file(label, ext=".json"):
    return os.path.join(jobs_dir(), key(label) + ext)


def _write(label, **state):
    tmp = _file(label, ".tmp%d" % os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, _file(label))


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parent_of(pid):
    """Windows: the parent of ``pid`` (Toolhelp snapshot), or 0."""
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k = ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    e = Entry()
    e.dwSize = ctypes.sizeof(Entry)
    found = 0
    try:
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.th32ProcessID == pid:
                found = e.th32ParentProcessID
                break
            ok = k.Process32NextW(snap, ctypes.byref(e))
    finally:
        k.CloseHandle(snap)
    return found


def host_pid():
    """radspider's process, seen from a tool or segmentation run. On Windows a venv's ``python.exe`` is a launcher
    that starts the real interpreter, so radspider is one level further up."""
    pid = os.getppid()
    if os.name == "nt" and getattr(sys, "_base_executable", sys.executable) != sys.executable:
        pid = _parent_of(pid) or pid
    return pid


def state(label):
    """The job of one set of weights: ``None`` (no job), or ``{"pid", "fraction", "error"}`` with ``running``."""
    try:
        with open(_file(label), encoding="utf-8") as f:
            s = json.load(f)
    except (FileNotFoundError, ValueError):
        return None
    s["running"] = not s.get("error") and alive(s.get("pid"))
    if not s["running"] and not s.get("error"):  # the worker died without a word (killed, radspider gone)
        _remove(_file(label))
        return None
    return s


def start(label):
    """Starts the worker for ``label`` unless one runs (a failed job is started again); returns its state."""
    s = state(label)
    if s and s["running"]:
        return s
    _remove(_file(label, ".stop"))
    import radspider_plugin

    sdk = os.path.dirname(os.path.abspath(radspider_plugin.__file__))
    here = os.path.dirname(os.path.abspath(__file__))
    args = [sys.executable, "-E", "-s", "-u", os.path.abspath(__file__), sdk, here, label, str(host_pid())]
    log = open(_file(label, ".log"), "w", encoding="utf-8")
    kw = {"start_new_session": True}
    if os.name == "nt":  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kw = {"creationflags": 0x00000200 | 0x08000000}
    p = subprocess.Popen(args, cwd=here, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **kw)
    log.close()
    _write(label, pid=p.pid, fraction=0.0, error=None)
    return state(label)


def stop(label, grace=3.0):
    """Asks the worker to stop (it removes its temporary files), and kills it after ``grace`` seconds."""
    s = state(label)
    if s and s["running"]:
        open(_file(label, ".stop"), "w").close()
        end = time.monotonic() + grace
        while alive(s["pid"]) and time.monotonic() < end:
            time.sleep(0.1)
        if alive(s["pid"]):  # stuck in a step without progress (Hugging Face download, conversion)
            try:
                os.kill(s["pid"], signal.SIGTERM)
            except OSError:
                pass
    _remove(_file(label))
    _remove(_file(label, ".stop"))


def wait(label, progress, message):
    """Blocks while the job of ``label`` runs, mirroring its progress; raises with its error if it failed."""
    while True:
        s = state(label)
        if not s:
            return
        if s.get("error"):
            raise ValueError(s["error"])
        progress(float(s.get("fraction") or 0.0), message)
        time.sleep(POLL)


# ---- the worker ----------------------------------------------------------------------------------------------------


class Stopped(Exception):
    pass


def _work(label, host):
    import plugin  # the plugin's own module: its catalog and the fetch functions

    w = {x.label: x for x in plugin.catalog()}[label]
    stop_file = _file(label, ".stop")
    gone = threading.Event()

    def watch():  # radspider closed: stop, and do not wait for a step that never reports
        while alive(host):
            time.sleep(2.0)
        gone.set()
        time.sleep(10.0)
        os._exit(3)

    threading.Thread(target=watch, daemon=True).start()
    last = [0.0]

    def progress(f, message=""):
        if gone.is_set() or os.path.exists(stop_file):
            raise Stopped()
        now = time.monotonic()
        if now - last[0] >= POLL:
            last[0] = now
            _write(label, pid=os.getpid(), fraction=max(0.0, min(1.0, float(f) / w.convert_at)), error=None)

    _write(label, pid=os.getpid(), fraction=0.0, error=None)
    try:
        w.fetch(progress)
    except Stopped:
        pass
    except Exception as e:  # noqa: BLE001 - the window shows it
        _write(label, pid=os.getpid(), fraction=0.0, error=str(e)[:180] or type(e).__name__)
        raise
    else:
        _remove(_file(label))
        return
    _remove(_file(label))
    _remove(stop_file)


if __name__ == "__main__":
    # autoseg_jobs.py <sdk dir> <plugin dir> <label> <radspider pid>: the SDK first, as the host's script does.
    sys.path[0:1] = [sys.argv[1], sys.argv[2]]
    _work(sys.argv[3], int(sys.argv[4]))
