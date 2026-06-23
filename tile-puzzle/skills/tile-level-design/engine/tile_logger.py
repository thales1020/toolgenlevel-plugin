"""
Tile Level Simulator — Structured Event Logger
================================================
JSON-line logging for all significant events.
Used by tile_api.py, tile_mcp_server.py, and GUI.

Log file: tile_events.log (in app directory)
Format: one JSON object per line

Created by Tran Ngoc Hai | Telegram @OrangeTran
"""

import json, os, time, traceback

_LOG_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE = os.path.join(_LOG_DIR, "tile_events.log")
_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_ROTATED = 2


def _rotate_if_needed():
    if not os.path.exists(_LOG_FILE):
        return
    if os.path.getsize(_LOG_FILE) < _MAX_SIZE:
        return
    # Rotate: .log → .log.1, .log.1 → .log.2, drop .log.2+
    for i in range(_MAX_ROTATED, 0, -1):
        src = f"{_LOG_FILE}.{i}" if i > 0 else _LOG_FILE
        dst = f"{_LOG_FILE}.{i + 1}" if i < _MAX_ROTATED else None
        if src == _LOG_FILE:
            src_path = _LOG_FILE
        else:
            src_path = src
        if os.path.exists(src_path):
            if dst and i < _MAX_ROTATED:
                try:
                    os.replace(src_path, dst)
                except OSError:
                    pass
            elif i >= _MAX_ROTATED:
                try:
                    os.remove(src_path)
                except OSError:
                    pass
    # Rename current log
    try:
        os.replace(_LOG_FILE, f"{_LOG_FILE}.1")
    except OSError:
        pass


def log_event(event: str, **kwargs):
    """Log a structured event to tile_events.log."""
    _rotate_if_needed()
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
    }
    entry.update(kwargs)
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except OSError:
        pass


def log_error(source: str, message: str, exc: Exception = None):
    """Log an error event with optional traceback."""
    tb = traceback.format_exc() if exc else None
    log_event("error", source=source, message=message, traceback=tb)


def get_recent_logs(n: int = 50) -> list[dict]:
    """Read last N log entries."""
    if not os.path.exists(_LOG_FILE):
        return []
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except OSError:
        return []


def clear_logs():
    """Clear the log file."""
    try:
        with open(_LOG_FILE, "w") as f:
            pass
    except OSError:
        pass
