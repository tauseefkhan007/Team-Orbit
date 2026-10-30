"""NextStop - a local, explainable journey planner for Hack Day Haldia."""

from __future__ import annotations

import heapq
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterable, Iterator

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__, static_folder=None)
DB_PATH = os.path.join(app.root_path, "data.db")
app.config.update(
    SECRET_KEY=os.environ.get("NEXTSTOP_SECRET_KEY", "nextstop-local-dev-key-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("NEXTSTOP_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SEED_NETWORK_VERSION = 3

SEED_STOPS = [
    ("HIT Main Gate, Hatiberia", "Hatiberia", 8, 20),
    ("Brajalachak", "Brajalachak", 20, 12),
    ("Manjushree", "Manjushree", 30, 28),
    ("Haldia Township", "Township", 16, 48),
    ("City Centre, Haldia", "Central Haldia", 32, 38),
    ("Durgachak", "Durgachak", 50, 46),
    ("Sutahata", "Sutahata", 62, 42),
    ("Chaitanyapur", "Chaitanyapur", 69, 34),
    ("Kukrahati Ferry Ghat", "Ferry Ghat", 83, 18),
    ("Mahishadal", "Mahishadal", 79, 44),
    ("Nandakumar", "Nandakumar", 76, 62),
    ("Neemtouri", "Neemtouri", 65, 68),
    ("Tamluk", "Tamluk", 54, 76),
    ("Mecheda", "Mecheda", 42, 88),
    ("Nandigram Ferry Ghat", "Ferry Ghat", 88, 62),
    ("Esplanade, Kolkata", "Kolkata", 30, 100),
]

SEED_STOP_MODES = {
    "HIT Main Gate, Hatiberia": "bus,auto",
    "Brajalachak": "bus,auto",
    "Manjushree": "bus,auto",
    "Haldia Township": "bus,auto",
    "City Centre, Haldia": "bus,auto",
    "Durgachak": "bus,auto",
    "Sutahata": "bus,auto",
    "Chaitanyapur": "bus,auto",
    "Kukrahati Ferry Ghat": "bus,auto,ferry",
    "Mahishadal": "bus,auto",
    "Nandakumar": "bus,auto",
    "Neemtouri": "bus,auto",
    "Tamluk": "bus,auto",
    "Mecheda": "bus,auto",
    "Nandigram Ferry Ghat": "bus,auto,ferry",
    "Esplanade, Kolkata": "bus",
}

SEED_ROUTES = [
    ("Orbit Red", "bus", "#e47225", "HIT Main Gate to Esplanade corridor"),
    ("Orbit Blue", "bus", "#e2007a", "Haldia Township to Nandakumar corridor"),
    ("Harbour Link", "ferry", "#6b7280", "Chaitanyapur to Nandakumar via Kukrahati"),
    ("Town Loop", "auto", "#9ca3af", "Shared auto through central Haldia"),
    ("Riverside", "bus", "#6b7280", "Chaitanyapur to Mecheda via Nandakumar"),
    ("South Connector", "bus", "#e2007a", "Nandigram Ferry Ghat to Tamluk"),
    ("Port Shuttle", "bus", "#16a34a", "Mecheda to Esplanade connector"),
    ("Nandigram Ferry", "ferry", "#e47225", "Nandigram Ferry Ghat connection"),
]

SEED_ROUTE_STOPS = {
    "Orbit Red": ["HIT Main Gate, Hatiberia", "Brajalachak", "Manjushree", "Haldia Township", "City Centre, Haldia", "Durgachak", "Sutahata", "Chaitanyapur", "Nandakumar", "Neemtouri", "Tamluk", "Mecheda", "Esplanade, Kolkata"],
    "Orbit Blue": ["Haldia Township", "City Centre, Haldia", "Durgachak", "Sutahata", "Chaitanyapur", "Nandakumar"],
    "Harbour Link": ["Chaitanyapur", "Kukrahati Ferry Ghat", "Mahishadal", "Nandakumar"],
    "Town Loop": ["Manjushree", "Haldia Township", "City Centre, Haldia", "Durgachak", "Sutahata"],
    "Riverside": ["Chaitanyapur", "Nandakumar", "Neemtouri", "Tamluk", "Mecheda"],
    "South Connector": ["Nandigram Ferry Ghat", "Nandakumar", "Neemtouri", "Tamluk"],
    "Port Shuttle": ["Mecheda", "Esplanade, Kolkata"],
    "Nandigram Ferry": ["Nandigram Ferry Ghat", "Nandakumar", "Mahishadal"],
}

SEED_COORDS = {
    # Anchors are intentionally kept in the local Haldia / Nandakumar area so
    # the Leaflet view follows the real geography instead of a flat mock map.
    "HIT Main Gate, Hatiberia": (22.0520, 88.0740),
    "Brajalachak": (22.0896, 88.0413),
    "Manjushree": (22.0550, 88.0830),
    "Haldia Township": (22.0233, 88.0590),
    "City Centre, Haldia": (22.0629, 88.0838),
    "Durgachak": (22.0713, 88.1376),
    "Sutahata": (22.1214, 88.1096),
    "Chaitanyapur": (22.1358, 88.0833),
    "Kukrahati Ferry Ghat": (22.1889, 88.1207),
    "Mahishadal": (22.1888, 87.9833),
    "Nandakumar": (22.1907, 87.9276),
    "Neemtouri": (22.2550, 87.9420),
    "Tamluk": (22.3003, 87.9180),
    "Mecheda": (22.4100, 87.8600),
    "Nandigram Ferry Ghat": (22.0900, 87.9850),
    "Esplanade, Kolkata": (22.5650, 88.3517),
}

SEED_TIMETABLES = {
    "Orbit Red": ("05:30", "22:30", 15),
    "Orbit Blue": ("06:00", "21:30", 20),
    "Harbour Link": ("06:15", "20:45", 30),
    "Town Loop": ("06:30", "22:00", 12),
    "Riverside": ("06:00", "21:00", 25),
    "South Connector": ("06:30", "20:30", 30),
    "Port Shuttle": ("05:45", "22:15", 20),
    "Nandigram Ferry": ("06:15", "20:45", 30),
}

DEFAULT_TIMETABLES = {
    "bus": ("06:00", "22:00", 20),
    "ferry": ("06:15", "20:45", 30),
    "auto": ("06:30", "22:00", 15),
}

LEGACY_SEED_STOP_NAMES = {
    "Haldia Township", "City Centre", "Durgachak", "Haldia Dock", "Haldia Port",
    "B.C. Roy Hospital", "Chaitanyapur", "Sutahata", "Kukrahati Ferry", "Mahishadal",
    "Balughata", "Dhalghata", "Sahid Matangini", "Nandakumar", "Rajendrapur",
    "Bhabanipur", "Bara Kamara",
}
LEGACY_STOP_RENAMES = {
    "City Centre": "City Centre, Haldia",
    "Kukrahati Ferry": "Kukrahati Ferry Ghat",
}
LEGACY_SEED_ROUTE_NAMES = {
    "Orbit Red", "Orbit Blue", "Harbour Link", "Town Loop", "Riverside",
    "South Connector", "Port Shuttle", "Nandigram Ferry",
}


def _segment_time(mode: str, index: int) -> int:
    base = {"bus": 7, "ferry": 14, "auto": 5}.get(mode, 8)
    return base + (index % 3) * 2


def _segment_fare(mode: str, index: int) -> int:
    base = {"bus": 10, "ferry": 18, "auto": 8}.get(mode, 0)
    return base + (index % 2) * 2


def _ensure_timetables(conn: sqlite3.Connection) -> None:
    """Give every route a simple, editable service window for live departure lookups."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS route_schedules (
            route_id INTEGER PRIMARY KEY REFERENCES routes(id),
            service_start TEXT NOT NULL,
            service_end TEXT NOT NULL,
            headway_minutes INTEGER NOT NULL DEFAULT 20,
            weekdays TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6'
        )
        """
    )
    routes = conn.execute("SELECT id, name, mode FROM routes").fetchall()
    for route in routes:
        start, end, headway = SEED_TIMETABLES.get(route["name"], DEFAULT_TIMETABLES.get(route["mode"], DEFAULT_TIMETABLES["bus"]))
        conn.execute(
            """
            INSERT OR IGNORE INTO route_schedules(route_id, service_start, service_end, headway_minutes)
            VALUES (?, ?, ?, ?)
            """,
            (route["id"], start, end, headway),
        )


def _clock_seconds(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":", 1))
    return (hour * 60 + minute) * 60


def _clock_label(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _next_departures(conn: sqlite3.Connection, route_name: str, now: datetime | None = None) -> dict:
    """Return the next three departures for the first service used by a journey."""
    route = conn.execute("SELECT id, mode FROM routes WHERE name = ?", (route_name,)).fetchone()
    if not route:
        return {"route": route_name, "status": "On demand", "departures": []}
    schedule = conn.execute("SELECT * FROM route_schedules WHERE route_id = ?", (route["id"],)).fetchone()
    if not schedule:
        return {"route": route_name, "status": "On demand", "departures": []}

    now = now or datetime.now()
    start_seconds = _clock_seconds(schedule["service_start"])
    end_seconds = _clock_seconds(schedule["service_end"])
    headway_seconds = max(60, int(schedule["headway_minutes"]) * 60)
    weekdays = {int(day) for day in schedule["weekdays"].split(",") if day.strip().isdigit()}
    departures = []

    for day_offset in range(8):
        service_day = now + timedelta(days=day_offset)
        if service_day.weekday() not in weekdays:
            continue
        service_start = service_day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=start_seconds)
        service_end = service_day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=end_seconds)
        departure = service_start
        while departure <= service_end:
            if departure >= now:
                departures.append(departure)
                if len(departures) == 3:
                    break
            departure += timedelta(seconds=headway_seconds)
        if len(departures) == 3:
            break

    departure_data = [
        {"at": departure.isoformat(), "label": _clock_label(departure)}
        for departure in departures
    ]
    next_departure = departures[0] if departures else None
    wait_seconds = (next_departure - now).total_seconds() if next_departure else None
    wait_minutes = max(0, int((wait_seconds + 59) // 60)) if wait_seconds is not None else None
    if not next_departure:
        status = "No service"
    elif next_departure.date() == now.date():
        status = "Running"
    elif (next_departure.date() - now.date()).days == 1:
        status = "Starts tomorrow"
    else:
        status = f"Starts {next_departure.strftime('%A')}"
    return {
        "route": route_name,
        "mode": route["mode"],
        "service_start": schedule["service_start"],
        "service_end": schedule["service_end"],
        "headway_minutes": schedule["headway_minutes"],
        "status": status,
        "wait_minutes": wait_minutes,
        "next_departure_at": next_departure.isoformat() if next_departure else None,
        "next_departure_label": _clock_label(next_departure) if next_departure else "No service",
        "departures": departure_data,
    }


def _rebuild_seed_network(conn: sqlite3.Connection) -> None:
    """Replace only the built-in demo network while preserving users and custom stops."""
    route_names = sorted(LEGACY_SEED_ROUTE_NAMES | {route[0] for route in SEED_ROUTES})
    placeholders = ",".join("?" for _ in route_names)
    route_rows = conn.execute(f"SELECT id FROM routes WHERE name IN ({placeholders})", route_names).fetchall()
    route_ids = [row["id"] for row in route_rows]
    if route_ids:
        conn.executemany("DELETE FROM edges WHERE route_id = ?", [(route_id,) for route_id in route_ids])
        conn.executemany("DELETE FROM route_schedules WHERE route_id = ?", [(route_id,) for route_id in route_ids])
        conn.executemany("DELETE FROM routes WHERE id = ?", [(route_id,) for route_id in route_ids])

    for old_name, new_name in LEGACY_STOP_RENAMES.items():
        old_row = conn.execute("SELECT id FROM stops WHERE name = ?", (old_name,)).fetchone()
        new_row = conn.execute("SELECT id FROM stops WHERE name = ?", (new_name,)).fetchone()
        if old_row and not new_row:
            conn.execute("UPDATE stops SET name = ? WHERE id = ?", (new_name, old_row["id"]))
        elif old_row and new_row:
            conn.execute(
                "DELETE FROM stops WHERE id = ? AND NOT EXISTS (SELECT 1 FROM edges WHERE from_stop = ? OR to_stop = ?)",
                (old_row["id"], old_row["id"], old_row["id"]),
            )

    legacy_only = LEGACY_SEED_STOP_NAMES - {stop[0] for stop in SEED_STOPS} - set(LEGACY_STOP_RENAMES)
    for old_name in legacy_only:
        conn.execute(
            "DELETE FROM stops WHERE name = ? AND NOT EXISTS (SELECT 1 FROM edges WHERE from_stop = stops.id OR to_stop = stops.id)",
            (old_name,),
        )

    for name, neighborhood, x, y in SEED_STOPS:
        lat, lng = SEED_COORDS.get(name, (None, None))
        modes = SEED_STOP_MODES.get(name, "bus,auto")
        existing = conn.execute("SELECT id FROM stops WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE stops SET neighborhood = ?, modes = ?, x = ?, y = ?, lat = ?, lng = ? WHERE id = ?",
                (neighborhood, modes, x, y, lat, lng, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO stops(name, neighborhood, modes, x, y, lat, lng) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, neighborhood, modes, x, y, lat, lng),
            )

    conn.executemany(
        "INSERT INTO routes(name, mode, color, description) VALUES (?, ?, ?, ?)",
        SEED_ROUTES,
    )
    stop_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM stops")}
    route_rows = conn.execute("SELECT id, name, mode FROM routes WHERE name IN ({})".format(placeholders), route_names).fetchall()
    route_data = {row["name"]: row for row in route_rows}
    edges = []
    for route_name, stop_names in SEED_ROUTE_STOPS.items():
        route = route_data[route_name]
        for index, (left, right) in enumerate(zip(stop_names, stop_names[1:])):
            minutes = _segment_time(route["mode"], index)
            fare = _segment_fare(route["mode"], index)
            edges.extend(
                [
                    (route["id"], stop_ids[left], stop_ids[right], minutes, fare),
                    (route["id"], stop_ids[right], stop_ids[left], minutes, fare),
                ]
            )
    conn.executemany(
        "INSERT INTO edges(route_id, from_stop, to_stop, minutes, fare) VALUES (?, ?, ?, ?, ?)",
        edges,
    )
    _ensure_timetables(conn)
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('seed_network_version', ?)",
        (str(SEED_NETWORK_VERSION),),
    )


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS stops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                neighborhood TEXT NOT NULL DEFAULT '',
                modes TEXT NOT NULL DEFAULT 'bus,auto',
                x INTEGER NOT NULL DEFAULT 50,
                y INTEGER NOT NULL DEFAULT 50,
                lat REAL,
                lng REAL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                home_city TEXT NOT NULL DEFAULT 'Haldia',
                travel_preference TEXT NOT NULL DEFAULT 'time',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                color TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL REFERENCES routes(id),
                from_stop INTEGER NOT NULL REFERENCES stops(id),
                to_stop INTEGER NOT NULL REFERENCES stops(id),
                minutes INTEGER NOT NULL,
                fare INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS route_schedules (
                route_id INTEGER PRIMARY KEY REFERENCES routes(id),
                service_start TEXT NOT NULL,
                service_end TEXT NOT NULL,
                headway_minutes INTEGER NOT NULL DEFAULT 20,
                weekdays TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6'
            );
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        stop_columns = {row["name"] for row in conn.execute("PRAGMA table_info(stops)").fetchall()}
        if "modes" not in stop_columns:
            conn.execute("ALTER TABLE stops ADD COLUMN modes TEXT NOT NULL DEFAULT 'bus,auto'")
        if "lat" not in stop_columns:
            conn.execute("ALTER TABLE stops ADD COLUMN lat REAL")
        if "lng" not in stop_columns:
            conn.execute("ALTER TABLE stops ADD COLUMN lng REAL")
        version = conn.execute("SELECT value FROM app_meta WHERE key = 'seed_network_version'").fetchone()
        if not version or version["value"] != str(SEED_NETWORK_VERSION):
            _rebuild_seed_network(conn)
        else:
            conn.executemany("UPDATE routes SET color = ? WHERE name = ?", [(route[2], route[0]) for route in SEED_ROUTES])
            conn.executemany("UPDATE stops SET lat = ?, lng = ? WHERE name = ?", [(lat, lng, name) for name, (lat, lng) in SEED_COORDS.items()])
            conn.executemany("UPDATE stops SET modes = ? WHERE name = ?", [(modes, name) for name, modes in SEED_STOP_MODES.items()])
            _ensure_timetables(conn)


init_db()


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VALID_PREFERENCES = {"time", "fare", "transfers"}


def _public_user(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "home_city": row["home_city"],
        "travel_preference": row["travel_preference"],
        "created_at": row["created_at"],
    }


def _session_user(conn: sqlite3.Connection) -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def _validate_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include at least one letter and one number"
    return None


def _find_stop(conn: sqlite3.Connection, value: str | None) -> sqlite3.Row | None:
    if not value:
        return None
    return conn.execute(
        "SELECT * FROM stops WHERE lower(name) = lower(?) OR CAST(id AS TEXT) = ?",
        (value.strip(), value.strip()),
    ).fetchone()


def _load_edges(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT e.*, r.name AS route_name, r.mode, r.color,
               s1.name AS from_name, s2.name AS to_name
        FROM edges e
        JOIN routes r ON r.id = e.route_id
        JOIN stops s1 ON s1.id = e.from_stop
        JOIN stops s2 ON s2.id = e.to_stop
        """
    ).fetchall()


def _path_cost(objective: str, minutes: int, fare: int, transfers: int) -> tuple[int, int, int]:
    """Return a lexicographic cost so the selected objective always wins."""
    if objective == "fare":
        return fare, minutes, transfers
    if objective == "transfers":
        return transfers, minutes, fare
    return minutes, transfers, fare


def _search(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
    objective: str,
    blocked_edges: Iterable[int] = (),
    delayed_route: str | None = None,
) -> dict | None:
    edges = _load_edges(conn)
    adjacency: dict[int, list[sqlite3.Row]] = {}
    blocked = set(blocked_edges)
    for edge in edges:
        adjacency.setdefault(edge["from_stop"], []).append(edge)

    queue = [(_path_cost(objective, 0, 0, 0), 0, 0, 0, source_id, None, [], [source_id])]
    best: dict[tuple[int, int | None], tuple[int, int, int]] = {}
    while queue:
        cost, minutes, fare, transfers, stop_id, current_route, path_edges, path_stops = heapq.heappop(queue)
        state_key = (stop_id, current_route)
        if cost > best.get(state_key, (float("inf"), float("inf"), float("inf"))):
            continue
        if stop_id == target_id and path_edges:
            stop_names = {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM stops").fetchall()}
            segments = []
            for edge in path_edges:
                delay = 12 if delayed_route and edge["route_name"] == delayed_route else 0
                segments.append(
                    {
                        "from": edge["from_name"],
                        "to": edge["to_name"],
                        "route": edge["route_name"],
                        "mode": edge["mode"],
                        "color": edge["color"],
                        "minutes": edge["minutes"] + delay,
                        "fare": edge["fare"],
                    }
                )
            return {
                "edge_ids": [edge["id"] for edge in path_edges],
                "stops": [stop_names[stop] for stop in path_stops],
                "segments": segments,
                "total_minutes": minutes,
                "total_fare": fare,
                "transfers": transfers,
                "routes": list(dict.fromkeys(segment["route"] for segment in segments)),
            }

        for edge in adjacency.get(stop_id, []):
            if edge["id"] in blocked:
                continue
            transfer = int(current_route is not None and current_route != edge["route_id"])
            delay = 12 if delayed_route and edge["route_name"] == delayed_route else 0
            new_minutes = minutes + edge["minutes"] + delay
            new_fare = fare + edge["fare"]
            new_transfers = transfers + transfer
            new_cost = _path_cost(objective, new_minutes, new_fare, new_transfers)
            next_key = (edge["to_stop"], edge["route_id"])
            if new_cost >= best.get(next_key, (float("inf"), float("inf"), float("inf"))):
                continue
            best[next_key] = new_cost
            heapq.heappush(
                queue,
                (
                    new_cost,
                    new_minutes,
                    new_fare,
                    new_transfers,
                    edge["to_stop"],
                    edge["route_id"],
                    path_edges + [edge],
                    path_stops + [edge["to_stop"]],
                ),
            )
    return None


def _alternatives(conn: sqlite3.Connection, source_id: int, target_id: int, objective: str, delayed_route: str | None) -> list[dict]:
    first = _search(conn, source_id, target_id, objective, delayed_route=delayed_route)
    if not first:
        return []
    results = [first]
    def signature(route: dict) -> tuple[tuple[str, str, str], ...]:
        return tuple((segment["from"], segment["to"], segment["route"]) for segment in route["segments"])

    def cost(route: dict) -> tuple[int, int, int]:
        return _path_cost(objective, route["total_minutes"], route["total_fare"], route["transfers"])

    signatures = {signature(first)}
    queued_signatures: set[tuple[tuple[str, str, str], ...]] = set()
    candidates: list[tuple[tuple[int, int, int], int, dict, frozenset[int]]] = []
    queued_block_sets: set[frozenset[int]] = set()
    sequence = 0

    def add_candidate(blocked_edges: frozenset[int]) -> None:
        nonlocal sequence
        if blocked_edges in queued_block_sets:
            return
        queued_block_sets.add(blocked_edges)
        alternative = _search(
            conn,
            source_id,
            target_id,
            objective,
            blocked_edges=blocked_edges,
            delayed_route=delayed_route,
        )
        if not alternative:
            return
        route_signature = signature(alternative)
        if route_signature in signatures or route_signature in queued_signatures:
            return
        queued_signatures.add(route_signature)
        heapq.heappush(candidates, (cost(alternative), sequence, alternative, blocked_edges))
        sequence += 1

    for edge_id in first["edge_ids"]:
        add_candidate(frozenset({edge_id}))
    while candidates and len(results) < 3:
        _, _, alternative, blocked_edges = heapq.heappop(candidates)
        route_signature = signature(alternative)
        if route_signature in signatures:
            continue
        signatures.add(route_signature)
        results.append(alternative)
        for edge_id in alternative["edge_ids"]:
            add_candidate(blocked_edges | {edge_id})
    return results[:3]


@app.get("/")
def home():
    return send_from_directory(app.root_path, "index.html")


@app.get("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(os.path.join(app.root_path, "assets"), filename)


@app.get("/api/health")
def health():
    with db() as conn:
        return jsonify(
            ok=True,
            product="NextStop",
            stops=conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0],
            routes=conn.execute("SELECT COUNT(*) FROM routes").fetchone()[0],
        )


@app.get("/api/auth/me")
def auth_me():
    with db() as conn:
        user = _session_user(conn)
        return jsonify(authenticated=user is not None, user=_public_user(user))


@app.post("/api/auth/register")
def auth_register():
    payload = request.get_json(silent=True) or {}
    full_name = str(payload.get("full_name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    home_city = str(payload.get("home_city", "Haldia")).strip() or "Haldia"
    preference = str(payload.get("travel_preference", "time")).strip().lower()
    if len(full_name) < 2 or len(full_name) > 80:
        return jsonify(error="Enter your full name"), 400
    if not EMAIL_RE.fullmatch(email):
        return jsonify(error="Enter a valid email address"), 400
    password_error = _validate_password(password)
    if password_error:
        return jsonify(error=password_error), 400
    if preference not in VALID_PREFERENCES:
        return jsonify(error="Choose a valid travel preference"), 400

    with db() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users(full_name, email, password_hash, home_city, travel_preference)
                VALUES (?, ?, ?, ?, ?)
                """,
                (full_name, email, generate_password_hash(password), home_city, preference),
            )
        except sqlite3.IntegrityError:
            return jsonify(error="An account with this email already exists"), 409
        user = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        return jsonify(user=_public_user(user)), 201


@app.post("/api/auth/login")
def auth_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify(error="Email or password is incorrect"), 401
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        return jsonify(user=_public_user(user))


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify(ok=True)


@app.put("/api/profile")
def update_profile():
    payload = request.get_json(silent=True) or {}
    full_name = str(payload.get("full_name", "")).strip()
    home_city = str(payload.get("home_city", "Haldia")).strip() or "Haldia"
    preference = str(payload.get("travel_preference", "time")).strip().lower()
    if len(full_name) < 2 or len(full_name) > 80:
        return jsonify(error="Enter your full name"), 400
    if preference not in VALID_PREFERENCES:
        return jsonify(error="Choose a valid travel preference"), 400
    with db() as conn:
        user = _session_user(conn)
        if not user:
            return jsonify(error="Please sign in to edit your profile"), 401
        conn.execute(
            """
            UPDATE users
            SET full_name = ?, home_city = ?, travel_preference = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (full_name, home_city, preference, user["id"]),
        )
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return jsonify(user=_public_user(updated))


@app.route("/api/stops", methods=["GET", "POST"])
def api_stops():
    with db() as conn:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            name = str(payload.get("name", "")).strip()
            if not name:
                return jsonify(error="Stop name is required"), 400
            modes = str(payload.get("modes", "bus,auto")).strip() or "bus,auto"
            try:
                cursor = conn.execute(
                    "INSERT INTO stops(name, neighborhood, modes, x, y) VALUES (?, ?, ?, ?, ?)",
                    (name, payload.get("neighborhood", "Local"), modes, int(payload.get("x", 50)), int(payload.get("y", 50))),
                )
                row = conn.execute("SELECT * FROM stops WHERE id = ?", (cursor.lastrowid,)).fetchone()
            except sqlite3.IntegrityError:
                return jsonify(error="A stop with that name already exists"), 409
            return jsonify(dict(row)), 201

        query = request.args.get("q", "").strip()
        rows = conn.execute("SELECT * FROM stops WHERE name LIKE ? ORDER BY name", (f"%{query}%",)).fetchall()
        return jsonify(stops=[dict(row) for row in rows])


@app.route("/api/routes", methods=["GET", "POST"])
def api_routes():
    with db() as conn:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                return jsonify(error="Expected a JSON object"), 400
            name = str(payload.get("name", "")).strip()
            mode = str(payload.get("mode", "bus")).strip().lower()
            raw_stops = payload.get("stops", [])
            if isinstance(raw_stops, str):
                delimiter = "\n" if "\n" in raw_stops else ","
                raw_stops = [item.strip() for item in raw_stops.split(delimiter) if item.strip()]
            if not isinstance(raw_stops, list):
                return jsonify(error="Stops must be provided as a list or a newline-separated string"), 400
            stop_names = [str(item).strip() for item in raw_stops if str(item).strip()]
            if not name or len(name) > 80:
                return jsonify(error="Route name must be between 1 and 80 characters"), 400
            if mode not in {"bus", "ferry", "auto"}:
                return jsonify(error="Choose bus, ferry, or auto for the route mode"), 400
            if len(stop_names) < 2:
                return jsonify(error="A route needs at least two stops"), 400
            color = str(payload.get("color", "#4f8cff")).strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                return jsonify(error="Route color must be a six-digit hex color"), 400
            stop_rows = [_find_stop(conn, item) for item in stop_names]
            if any(row is None for row in stop_rows):
                return jsonify(error="Every route stop must already exist in the network"), 400
            try:
                minutes = int(payload.get("minutes", _segment_time(mode, 0)))
                fare = int(payload.get("fare", _segment_fare(mode, 0)))
            except (TypeError, ValueError):
                return jsonify(error="Minutes and fare must be whole numbers"), 400
            if minutes < 1 or minutes > 1440 or fare < 0 or fare > 1000000:
                return jsonify(error="Minutes must be 1–1440 and fare must be 0–1000000"), 400
            try:
                cursor = conn.execute(
                    "INSERT INTO routes(name, mode, color, description) VALUES (?, ?, ?, ?)",
                    (name, mode, color, str(payload.get("description", "")).strip()[:240]),
                )
            except sqlite3.IntegrityError:
                return jsonify(error="A route with that name already exists"), 409
            edges = []
            for left, right in zip(stop_rows, stop_rows[1:]):
                edges.extend(
                    [
                        (cursor.lastrowid, left["id"], right["id"], minutes, fare),
                        (cursor.lastrowid, right["id"], left["id"], minutes, fare),
                    ]
                )
            conn.executemany(
                "INSERT INTO edges(route_id, from_stop, to_stop, minutes, fare) VALUES (?, ?, ?, ?, ?)",
                edges,
            )
            _ensure_timetables(conn)
            row = conn.execute("SELECT * FROM routes WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return jsonify({**dict(row), "stops": stop_names}), 201

        rows = conn.execute("SELECT * FROM routes ORDER BY name").fetchall()
        return jsonify(routes=[dict(row) for row in rows])


@app.get("/api/route")
def api_route():
    source = request.args.get("from")
    target = request.args.get("to")
    objective = request.args.get("mode", "time")
    delayed_route = request.args.get("delay_route") or None
    if objective not in {"time", "fare", "transfers"}:
        return jsonify(error="mode must be time, fare, or transfers"), 400
    if not source or not target:
        return jsonify(error="from and to are required"), 400

    with db() as conn:
        start = _find_stop(conn, source)
        end = _find_stop(conn, target)
        if not start or not end:
            return jsonify(error="Choose valid start and destination stops"), 404
        if start["id"] == end["id"]:
            return jsonify(error="Start and destination must be different"), 400
        routes = _alternatives(conn, start["id"], end["id"], objective, delayed_route)
        if not routes:
            return jsonify(error="No route found between these stops", routes=[]), 404
        now = datetime.now()
        for route in routes:
            first_service = route["routes"][0] if route["routes"] else None
            route["schedule"] = _next_departures(conn, first_service, now) if first_service else None
        return jsonify(
            product="NextStop",
            from_stop=dict(start),
            to_stop=dict(end),
            mode=objective,
            delayed_route=delayed_route,
            generated_at=now.isoformat(),
            routes=routes,
        )


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5001)),
    )
