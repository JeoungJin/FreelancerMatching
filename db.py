import sqlite3
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "matching.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(schema_sql: str) -> None:
    with get_conn() as conn:
        conn.executescript(schema_sql)

def upsert_skill(conn: sqlite3.Connection, name: str, skill_type: str = "etc") -> int:
    cur = conn.execute(
        "INSERT INTO skills(skill_name, skill_type) VALUES (?, ?) "
        "ON CONFLICT(skill_name) DO UPDATE SET skill_type=excluded.skill_type "
        "RETURNING skill_id;",
        (name.strip(), skill_type.strip())
    )
    row = cur.fetchone()
    return int(row["skill_id"])

def create_developer(
    name: str,
    role: str,
    total_career_years: float,
    headline: Optional[str] = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO developers(name, role, total_career_years, headline) VALUES (?, ?, ?, ?)",
            (name, role, total_career_years, headline)
        )
        return int(cur.lastrowid)

def save_developer_skills(developer_id: int, skills: List[Dict[str, Any]]) -> None:
    """
    skills 예:
    [{"name":"Java","level":5,"experience_years":4,"type":"language","is_primary":1}, ...]
    """
    with get_conn() as conn:
        for s in skills:
            skill_id = upsert_skill(conn, s["name"], s.get("type", "etc"))
            conn.execute(
                """
                INSERT INTO developer_skills(developer_id, skill_id, skill_level, experience_years, last_used_at, is_primary)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(developer_id, skill_id) DO UPDATE SET
                  skill_level=excluded.skill_level,
                  experience_years=excluded.experience_years,
                  last_used_at=excluded.last_used_at,
                  is_primary=excluded.is_primary
                """,
                (
                    developer_id,
                    skill_id,
                    int(s.get("level", 3)),
                    float(s.get("experience_years", 0)),
                    s.get("last_used_at"),
                    int(s.get("is_primary", 0))
                )
            )

def create_company(company_name: str, industry: Optional[str] = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO companies(company_name, industry) VALUES (?, ?)",
            (company_name, industry)
        )
        return int(cur.lastrowid)

def create_project(
    company_id: int,
    project_name: str,
    description: str,
    min_total_career: float,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects(company_id, project_name, description, min_total_career) VALUES (?, ?, ?, ?)",
            (company_id, project_name, description, min_total_career)
        )
        return int(cur.lastrowid)

def save_project_requirements(project_id: int, reqs: List[Dict[str, Any]]) -> None:
    """
    reqs 예:
    [{"skill":"Java","min_level":4,"min_years":3,"weight":5,"mandatory":1,"type":"language"}, ...]
    """
    with get_conn() as conn:
        for r in reqs:
            skill_id = upsert_skill(conn, r["skill"], r.get("type", "etc"))
            conn.execute(
                """
                INSERT INTO project_requirements(project_id, skill_id, min_skill_level, min_experience_years, weight, is_mandatory)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, skill_id) DO UPDATE SET
                  min_skill_level=excluded.min_skill_level,
                  min_experience_years=excluded.min_experience_years,
                  weight=excluded.weight,
                  is_mandatory=excluded.is_mandatory
                """,
                (
                    project_id,
                    skill_id,
                    int(r.get("min_level", 3)),
                    float(r.get("min_years", 0)),
                    int(r.get("weight", 1)),
                    int(r.get("mandatory", 1)),
                )
            )

def list_open_projects() -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT p.*, c.company_name FROM projects p JOIN companies c ON p.company_id=c.company_id WHERE p.status='OPEN' ORDER BY p.created_at DESC"
        ).fetchall()

def list_developers() -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM developers ORDER BY created_at DESC"
        ).fetchall()

def get_project_requirements(project_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT pr.*, s.skill_name, s.skill_type
            FROM project_requirements pr
            JOIN skills s ON pr.skill_id=s.skill_id
            WHERE pr.project_id=?
            """,
            (project_id,)
        ).fetchall()

def get_developer_skills(developer_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT ds.*, s.skill_name, s.skill_type
            FROM developer_skills ds
            JOIN skills s ON ds.skill_id=s.skill_id
            WHERE ds.developer_id=?
            """,
            (developer_id,)
        ).fetchall()

def save_match(project_id: int, developer_id: int, score: int, reason: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO matches(project_id, developer_id, match_score, reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id, developer_id) DO UPDATE SET
              match_score=excluded.match_score,
              reason=excluded.reason,
              created_at=datetime('now')
            """,
            (project_id, developer_id, int(score), reason)
        )


def list_matches():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT m.match_id, m.project_id, m.developer_id, m.match_score, m.created_at,
                   p.project_name, c.company_name,
                   d.name AS developer_name
            FROM matches m
            JOIN projects p ON m.project_id=p.project_id
            JOIN companies c ON p.company_id=c.company_id
            JOIN developers d ON m.developer_id=d.developer_id
            ORDER BY m.created_at DESC
            """
        ).fetchall()

def get_match_detail(match_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM matches WHERE match_id=?",
            (match_id,)
        ).fetchone()
        return dict(row) if row else None
            