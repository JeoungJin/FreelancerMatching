import json
import streamlit as st
from dotenv import load_dotenv

import db
from matching import calc_match_score

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS

# -------------------------------------------------
# 환경 변수 로드
# -------------------------------------------------
load_dotenv()

# -------------------------------------------------
# Streamlit 설정
# -------------------------------------------------
st.set_page_config(page_title="Dev↔Project Matching (LangChain + RAG)", layout="wide")
st.title("💬 LangChain + RAG 기반 개발자-프로젝트 매칭")

# -------------------------------------------------
# LLM / Embeddings
# -------------------------------------------------
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
embeddings = OpenAIEmbeddings()

# -------------------------------------------------
# DB 스키마 로드
# -------------------------------------------------
SCHEMA_SQL = open("schema.sql", "r", encoding="utf-8").read()

# -------------------------------------------------
# Prompt Templates
# -------------------------------------------------
DEV_PROMPT = ChatPromptTemplate.from_template("""
너는 개발자 커리어를 구조화하는 AI다.
반드시 JSON만 출력해라. 설명 문장 금지.

형식:
{{
  "name": "",
  "role": "backend|frontend|fullstack|etc",
  "total_career_years": number,
  "headline": "",
  "skills": [
    {{"name":"", "type":"language|framework|db|tool|etc",
      "level":1~5, "experience_years": number, "is_primary":0|1}}
  ]
}}

입력:
{input}
""")

PROJECT_PROMPT = ChatPromptTemplate.from_template("""
너는 기업 프로젝트를 구조화하는 AI다.
반드시 JSON만 출력해라. 설명 문장 금지.

형식:
{{
  "company_name": "",
  "industry": "",
  "project_name": "",
  "description": "",
  "min_total_career": number,
  "requirements": [
    {{"skill":"", "type":"language|framework|db|tool|etc",
      "min_level":1~5, "min_years": number, "weight":1~5, "mandatory":true|false}}
  ]
}}

입력:
{input}
""")

RAG_EXPLAIN_PROMPT = ChatPromptTemplate.from_template("""
너는 개발자-프로젝트 매칭 AI다.

[프로젝트 설명]
{project_text}

[의미적으로 유사한 개발자 컨텍스트]
{rag_context}

위 정보를 참고하여,
왜 이 개발자가 이 프로젝트에 적합한지
기술적 관점에서 설명해라.
""")

# -------------------------------------------------
# Session State
# -------------------------------------------------
st.session_state.setdefault("mode", "개발자 등록")
st.session_state.setdefault("chat", [])

# -------------------------------------------------
# Sidebar
# -------------------------------------------------
with st.sidebar:
    st.header("설정")
    st.session_state.mode = st.radio(
        "화면 선택",
        ["개발자 등록", "기업/프로젝트 등록", "매칭 추천"]
    )

    if st.button("DB 스키마 적용"):
        db.init_db(SCHEMA_SQL)
        st.success("스키마 적용 완료")

    if st.button("대화 초기화"):
        st.session_state.chat = []
        st.rerun()

# -------------------------------------------------
# Helper Functions
# -------------------------------------------------
def dev_to_text(dev, skills):
    lines = [
        f"Role: {dev['role']}",
        f"Total career: {dev['total_career_years']} years"
    ]
    for s in skills:
        lines.append(
            f"{s['skill_name']} level {s['skill_level']} "
            f"with {s['experience_years']} years"
        )
    return "\n".join(lines)

def project_to_text(project, reqs):
    lines = [f"Minimum career: {project['min_total_career']} years"]
    for r in reqs:
        lines.append(
            f"{r['skill_name']} required level {r['min_skill_level']} "
            f"for {r['min_experience_years']} years"
        )
    return "\n".join(lines)

def score_bar(score):
    st.progress(score / 100)
    if score >= 85:
        st.success(f"적합도 {score}점 (강력 추천)")
    elif score >= 70:
        st.info(f"적합도 {score}점 (추천)")
    else:
        st.warning(f"적합도 {score}점 (조건 보완 필요)")

# -------------------------------------------------
# 개발자 등록
# -------------------------------------------------
if st.session_state.mode == "개발자 등록":
    st.subheader("👨‍💻 개발자 등록")
    text = st.text_area("개발자 커리어를 자연어로 입력하세요")

    if st.button("분석 & 저장"):
        res = (DEV_PROMPT | llm).invoke({"input": text})
        data = json.loads(res.content)

        dev_id = db.create_developer(
            name=data["name"],
            role=data["role"],
            total_career_years=data["total_career_years"],
            headline=data.get("headline")
        )
        db.save_developer_skills(dev_id, data["skills"])
        st.success(f"저장 완료 (developer_id={dev_id})")
        st.json(data)

# -------------------------------------------------
# 프로젝트 등록
# -------------------------------------------------
elif st.session_state.mode == "기업/프로젝트 등록":
    st.subheader("🏢 기업/프로젝트 등록")
    text = st.text_area("프로젝트 요구사항을 자연어로 입력하세요")

    if st.button("분석 & 저장"):
        res = (PROJECT_PROMPT | llm).invoke({"input": text})
        data = json.loads(res.content)

        company_id = db.create_company(data["company_name"], data.get("industry"))
        project_id = db.create_project(
            company_id,
            data["project_name"],
            data.get("description", ""),
            data["min_total_career"]
        )

        reqs = []
        for r in data["requirements"]:
            reqs.append({
                "skill": r["skill"],
                "type": r["type"],
                "min_level": r["min_level"],
                "min_years": r["min_years"],
                "weight": r["weight"],
                "mandatory": 1 if r["mandatory"] else 0
            })

        db.save_project_requirements(project_id, reqs)
        st.success(f"저장 완료 (project_id={project_id})")
        st.json(data)

# -------------------------------------------------
# 매칭 추천 (Rule + RAG)
# -------------------------------------------------
else:
    st.subheader("🤖 매칭 추천")

    projects = [dict(r) for r in db.list_open_projects()]
    devs = [dict(r) for r in db.list_developers()]

    if not projects or not devs:
        st.info("개발자와 프로젝트를 먼저 등록하세요.")
        st.stop()

    proj = st.selectbox(
        "프로젝트 선택",
        projects,
        format_func=lambda r: f"[{r['project_id']}] {r['project_name']}"
    )

    reqs = [dict(r) for r in db.get_project_requirements(proj["project_id"])]
    project_dict = {"min_total_career": proj["min_total_career"]}

    # -------- RAG: Vector Index 생성 --------
    docs, metas = [], []
    for d in devs:
        skills = [dict(s) for s in db.get_developer_skills(d["developer_id"])]
        docs.append(dev_to_text(d, skills))
        metas.append({"developer_id": d["developer_id"], "name": d["name"]})

    vectorstore = FAISS.from_texts(docs, embeddings, metadatas=metas)

    project_text = project_to_text(project_dict, reqs)
    rag_docs = vectorstore.similarity_search(project_text, k=3)
    rag_context = "\n\n".join(d.page_content for d in rag_docs)

    # -------- Rule 기반 점수 --------
    results = []
    for d in devs:
        skills = [dict(s) for s in db.get_developer_skills(d["developer_id"])]
        score, reason = calc_match_score(
            {"total_career_years": d["total_career_years"], "role": d["role"]},
            project_dict,
            skills,
            reqs
        )
        if score > 0:
            results.append((score, d, reason, skills))

    results.sort(key=lambda x: x[0], reverse=True)

    # -------- 출력 --------
    for score, d, reason, skills in results[:5]:
        with st.container(border=True):
            st.markdown(f"### ✅ {d['name']} ({d['role']})")
            score_bar(score)

            with st.expander("📊 Rule 기반 상세"):
                st.text(reason)

            with st.expander("🧠 RAG 기반 설명"):
                rag_res = (RAG_EXPLAIN_PROMPT | llm).invoke({
                    "project_text": project_text,
                    "rag_context": rag_context
                })
                st.markdown(rag_res.content)

            with st.expander("🧩 기술 스택"):
                st.json(skills)
