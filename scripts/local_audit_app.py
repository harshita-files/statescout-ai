"""StateScout local-site audit — takes a folder path. Run: ./run_local.sh  (port 8081)"""
from __future__ import annotations

import http.server
import pathlib
import threading
import uuid

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from scripts._audit_core import JOBS, run_audit
from scripts._frontend import page

app = FastAPI(title="StateScout Local Audit")
_FRONTEND = page("local")
DEMO_ROOT = pathlib.Path(__file__).resolve().parent.parent / "demo-inputs"
EXAMPLES = sorted(d.name for d in DEMO_ROOT.iterdir() if d.is_dir()) if DEMO_ROOT.is_dir() else []


# --- fixed-port static server ------------------------------------------------
# One long-lived server for the whole console session, serving whatever folder
# the current audit points at. A stable host:port means re-running the same
# folder yields the same URLs -> the same fingerprints -> Neo4j MERGEs onto the
# existing StateNodes instead of writing a fresh copy every run.
_PREFERRED_PORT = 8090
_serve_state: dict[str, str | None] = {"dir": None}
_httpd: http.server.ThreadingHTTPServer | None = None
_httpd_port: int | None = None
_audit_lock = threading.Lock()


class _DirHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=_serve_state["dir"] or ".", **kwargs)  # type: ignore[arg-type]

    def log_message(self, *args: object) -> None:  # keep the console quiet
        pass


def _ensure_httpd() -> int:
    global _httpd, _httpd_port
    if _httpd is not None:
        return _httpd_port  # type: ignore[return-value]
    for candidate in range(_PREFERRED_PORT, _PREFERRED_PORT + 20):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", candidate), _DirHandler)
        except OSError:
            continue
        _httpd = srv
        _httpd_port = candidate
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return candidate
    raise RuntimeError("no free port for the static file server")


def _resolve(path_str: str, entry: str) -> tuple[str, str]:
    root = pathlib.Path(path_str).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"No such folder: {root}")
    if not root.is_dir():
        raise ValueError(f"Not a folder: {root}")
    if entry.strip():
        if not (root / entry.strip()).is_file():
            raise ValueError(f"Entry file not found: {root / entry.strip()}")
        return str(root), entry.strip()
    for name in ("index.html", "index.htm"):
        if (root / name).is_file():
            return str(root), name
    htmls = sorted(p.name for p in root.glob("*.html"))
    if not htmls:
        raise ValueError(f"No .html file in {root} — pass an entry file, or point at a built site")
    return str(root), htmls[0]


class AuditRequest(BaseModel):
    path: str
    entry: str = ""
    policy: str
    role: str = "guest"
    max_states: int = 15
    depth_limit: int = 3
    use_vision: bool = True


def _run(job_id: str, path_str: str, entry: str, policy: str, role: str) -> None:
    try:
        abs_dir, entry_file = _resolve(path_str, entry)
    except ValueError as exc:
        j = JOBS[job_id]
        j["status"] = "error"
        j["error"] = f"ValueError: {exc}"
        j["log"].append("ERROR: " + j["error"])
        return

    # One audit at a time: the static server has a single "current directory".
    with _audit_lock:
        _serve_state["dir"] = abs_dir
        port = _ensure_httpd()
        base = f"http://127.0.0.1:{port}/"
        JOBS[job_id]["log"].append(f"serving {abs_dir} on 127.0.0.1:{port} (fixed)")

        def display(u: str | None) -> str | None:
            if not u:
                return None
            return abs_dir + "/" + u[len(base):] if u.startswith(base) else u

        run_audit(job_id, seed_url=base + entry_file, base_url=base, policy_text=policy,
                  role=role, display=display, label=abs_dir)


@app.post("/api/audit")
def start(req: AuditRequest) -> JSONResponse:
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "queued", "log": [], "result": None, "error": None,
        "max_states": max(1, min(req.max_states, 40)),
        "depth_limit": max(0, min(req.depth_limit, 6)),
        "use_vision": bool(req.use_vision),
    }
    threading.Thread(
        target=_run, args=(job_id, req.path.strip(), req.entry, req.policy, req.role.strip() or "guest"),
        daemon=True,
    ).start()
    return JSONResponse({"job_id": job_id})


@app.get("/api/audit/{job_id}")
def poll(job_id: str) -> JSONResponse:
    j = JOBS.get(job_id)
    if j is None:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return JSONResponse({"status": j["status"], "log": j["log"], "result": j["result"],
                         "error": j["error"], "policy_parsed": j.get("policy_parsed")})


@app.get("/api/examples")
def examples() -> JSONResponse:
    return JSONResponse({"root": str(DEMO_ROOT), "names": EXAMPLES})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FRONTEND
