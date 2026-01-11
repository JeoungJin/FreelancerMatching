PRAGMA foreign_keys = ON;

-- 기업(client)
CREATE TABLE IF NOT EXISTS companies (
  company_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_name TEXT NOT NULL,
  industry TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

-- 개발자(freelencer)
CREATE TABLE IF NOT EXISTS developers (
  developer_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  role TEXT NOT NULL,                -- backend/frontend/fullstack/etc
  total_career_years REAL NOT NULL DEFAULT 0,
  headline TEXT,                     -- 한 줄 소개(선택)
  created_at TEXT DEFAULT (datetime('now'))
);

-- client의 프로젝트
CREATE TABLE IF NOT EXISTS projects (
  project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL,
  project_name TEXT NOT NULL,
  description TEXT,
  min_total_career REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN/CLOSED
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
);

-- 기술 마스터 
CREATE TABLE IF NOT EXISTS skills (
  skill_id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_name TEXT NOT NULL UNIQUE,       -- Java, Spring, Oracle, IntelliJ
  skill_type TEXT NOT NULL,              -- language/framework/db/tool/etc
  parent_skill_id INTEGER,
  FOREIGN KEY (parent_skill_id) REFERENCES skills(skill_id) ON DELETE SET NULL
);

-- 개발자 보유 기술
CREATE TABLE IF NOT EXISTS developer_skills (
  developer_id INTEGER NOT NULL,
  skill_id INTEGER NOT NULL,
  skill_level INTEGER NOT NULL CHECK(skill_level BETWEEN 1 AND 5),
  experience_years REAL NOT NULL DEFAULT 0,
  last_used_at TEXT,
  is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0,1)),
  PRIMARY KEY (developer_id, skill_id),
  FOREIGN KEY (developer_id) REFERENCES developers(developer_id) ON DELETE CASCADE,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
);

-- 프로젝트 요구 기술
CREATE TABLE IF NOT EXISTS project_requirements (
  project_id INTEGER NOT NULL,
  skill_id INTEGER NOT NULL,
  min_skill_level INTEGER NOT NULL CHECK(min_skill_level BETWEEN 1 AND 5),
  min_experience_years REAL NOT NULL DEFAULT 0,
  weight INTEGER NOT NULL DEFAULT 1 CHECK(weight BETWEEN 1 AND 5),
  is_mandatory INTEGER NOT NULL DEFAULT 1 CHECK(is_mandatory IN (0,1)), --필수기술인지?
  PRIMARY KEY (project_id, skill_id),
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
  FOREIGN KEY (skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
);

-- 매칭 결과 캐시(선택)
CREATE TABLE IF NOT EXISTS matches (
  match_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  developer_id INTEGER NOT NULL,
  match_score INTEGER NOT NULL CHECK(match_score BETWEEN 0 AND 100),
  reason TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(project_id, developer_id),
  FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
  FOREIGN KEY (developer_id) REFERENCES developers(developer_id) ON DELETE CASCADE
);

-- 추천/조회 최적화용 인덱스
CREATE INDEX IF NOT EXISTS idx_dev_role ON developers(role);
CREATE INDEX IF NOT EXISTS idx_dev_total_career ON developers(total_career_years);
CREATE INDEX IF NOT EXISTS idx_proj_company ON projects(company_id);
CREATE INDEX IF NOT EXISTS idx_skill_name ON skills(skill_name);
CREATE INDEX IF NOT EXISTS idx_dev_skills_skill ON developer_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_proj_req_skill ON project_requirements(skill_id);
