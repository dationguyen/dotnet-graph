import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects (
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    path     TEXT NOT NULL UNIQUE,
    domain   TEXT,
    platform TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    path       TEXT NOT NULL UNIQUE,
    namespace  TEXT
);

CREATE TABLE IF NOT EXISTS types (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id),
    project_id  INTEGER REFERENCES projects(id),
    name        TEXT NOT NULL,
    full_name   TEXT,
    kind        TEXT,
    is_abstract INTEGER DEFAULT 0,
    is_partial  INTEGER DEFAULT 0,
    line        INTEGER
);

CREATE TABLE IF NOT EXISTS relationships (
    id        INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL,
    to_type   TEXT NOT NULL,
    kind      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usings (
    id        INTEGER PRIMARY KEY,
    file_id   INTEGER REFERENCES files(id),
    namespace TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS methods (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id),
    type_id     INTEGER REFERENCES types(id),
    project_id  INTEGER REFERENCES projects(id),
    name        TEXT NOT NULL,
    return_type TEXT,
    parameters  TEXT,
    visibility  TEXT,
    is_async    INTEGER DEFAULT 0,
    is_static   INTEGER DEFAULT 0,
    is_override INTEGER DEFAULT 0,
    line        INTEGER
);

CREATE TABLE IF NOT EXISTS properties (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id),
    type_id     INTEGER REFERENCES types(id),
    project_id  INTEGER REFERENCES projects(id),
    name        TEXT NOT NULL,
    type_name   TEXT,
    visibility  TEXT,
    is_static   INTEGER DEFAULT 0,
    line        INTEGER
);

CREATE TABLE IF NOT EXISTS xaml_views (
    id         INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    path       TEXT NOT NULL UNIQUE,
    x_class    TEXT,
    view_name  TEXT
);

CREATE TABLE IF NOT EXISTS registrations (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER REFERENCES files(id),
    project_id     INTEGER REFERENCES projects(id),
    interface_type TEXT,
    impl_type      TEXT,
    lifetime       TEXT,
    line           INTEGER
);

CREATE TABLE IF NOT EXISTS endpoints (
    id          INTEGER PRIMARY KEY,
    file_id     INTEGER REFERENCES files(id),
    project_id  INTEGER REFERENCES projects(id),
    type_name   TEXT,
    url_pattern TEXT,
    http_method TEXT,
    line        INTEGER
);

CREATE TABLE IF NOT EXISTS config_keys (
    id          INTEGER PRIMARY KEY,
    source_file TEXT,
    key_path    TEXT NOT NULL,
    value       TEXT,
    environment TEXT
);

CREATE TABLE IF NOT EXISTS features (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    domain      TEXT,
    viewmodel   TEXT,
    service     TEXT,
    project     TEXT
);

CREATE TABLE IF NOT EXISTS constructor_injections (
    id           INTEGER PRIMARY KEY,
    file_id      INTEGER REFERENCES files(id),
    type_id      INTEGER REFERENCES types(id),
    project_id   INTEGER REFERENCES projects(id),
    param_type   TEXT NOT NULL,
    param_name   TEXT NOT NULL,
    line         INTEGER
);

CREATE TABLE IF NOT EXISTS field_declarations (
    id           INTEGER PRIMARY KEY,
    file_id      INTEGER REFERENCES files(id),
    type_id      INTEGER REFERENCES types(id),
    project_id   INTEGER REFERENCES projects(id),
    name         TEXT NOT NULL,
    type_name    TEXT NOT NULL,
    visibility   TEXT,
    is_readonly  INTEGER DEFAULT 0,
    is_static    INTEGER DEFAULT 0,
    line         INTEGER
);

CREATE TABLE IF NOT EXISTS method_calls (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER REFERENCES files(id),
    caller_type_id  INTEGER REFERENCES types(id),
    caller_method   TEXT NOT NULL,
    callee_expr     TEXT NOT NULL,
    callee_method   TEXT NOT NULL,
    line            INTEGER
);

CREATE INDEX IF NOT EXISTS idx_types_name      ON types(name);
CREATE INDEX IF NOT EXISTS idx_types_full_name ON types(full_name);
CREATE INDEX IF NOT EXISTS idx_rel_from        ON relationships(from_type);
CREATE INDEX IF NOT EXISTS idx_rel_to          ON relationships(to_type);
CREATE INDEX IF NOT EXISTS idx_files_ns        ON files(namespace);
CREATE INDEX IF NOT EXISTS idx_methods_name    ON methods(name);
CREATE INDEX IF NOT EXISTS idx_methods_type    ON methods(type_id);
CREATE INDEX IF NOT EXISTS idx_props_name      ON properties(name);
CREATE INDEX IF NOT EXISTS idx_props_type      ON properties(type_id);
CREATE INDEX IF NOT EXISTS idx_endpoints_url   ON endpoints(url_pattern);
CREATE INDEX IF NOT EXISTS idx_config_key      ON config_keys(key_path);
CREATE INDEX IF NOT EXISTS idx_reg_iface       ON registrations(interface_type);
CREATE INDEX IF NOT EXISTS idx_ctor_type_id    ON constructor_injections(type_id);
CREATE INDEX IF NOT EXISTS idx_ctor_param_type ON constructor_injections(param_type);
CREATE INDEX IF NOT EXISTS idx_field_type_id   ON field_declarations(type_id);
CREATE INDEX IF NOT EXISTS idx_field_name      ON field_declarations(name);
CREATE INDEX IF NOT EXISTS idx_calls_caller    ON method_calls(caller_type_id, caller_method);
CREATE INDEX IF NOT EXISTS idx_calls_callee    ON method_calls(callee_method);
CREATE INDEX IF NOT EXISTS idx_calls_expr      ON method_calls(callee_expr);
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.row_factory = sqlite3.Row
    return conn


_VALID_TABLES = frozenset({
    "projects", "files", "types", "methods", "properties",
    "relationships", "usings", "xaml_views", "registrations",
    "endpoints", "config_keys", "features", "constructor_injections",
    "field_declarations", "method_calls",
})


def count(conn: sqlite3.Connection, table: str) -> int:
    if table not in _VALID_TABLES:
        raise ValueError(f"Unknown table: {table!r}")
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
