import db
from matching import calc_match_score
import json
import streamlit as st
#import pandas as pd
import numpy as np
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv # .env 파일의 환경변수를 자동으로 불러오기 위한 모듈

load_dotenv()  # 실행 시 .env 파일을 찾아 변수들을 환경에 로드

  

# ----------------------------
# 설정
# ----------------------------
st.set_page_config(page_title="Dev↔Project Matching (SQLite)", layout="wide")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

# schema.sql 읽기(파일로 저장해둔 DDL)
SCHEMA_SQL = open("schema.sql", "r", encoding="utf-8").read()

# ----------------------------
# 프롬프트
# ----------------------------
DEV_PROMPT = ChatPromptTemplate.from_template("""
너는 개발자 커리어를 구조화하는 AI다.
반드시 JSON만 출력해라. 마크다운/설명 문장 금지.

형식:
{{
  "name": "",
  "role": "backend|frontend|fullstack|etc",
  "total_career_years": number,
  "headline": "",
  "skills": [
    {{"name":"", "type":"language|framework|db|tool|etc", "level":1~5, "experience_years": number, "is_primary":0|1}}
  ]
}}

입력:
{input}
""")

PROJECT_PROMPT = ChatPromptTemplate.from_template("""
너는 기업 프로젝트를 구조화하는 AI다.
반드시 JSON만 출력해라. 마크다운/설명 문장 금지.

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

# ----------------------------
# 세션 상태
# ----------------------------
st.session_state.setdefault("chat_msgs", [])  # [{"role":"user|assistant","content":...}]
st.session_state.setdefault("mode", "개발자 등록")
st.session_state.setdefault("last_saved_dev_id", None)
st.session_state.setdefault("last_saved_project_id", None)

# ----------------------------
# 사이드바
# ----------------------------
with st.sidebar:
    st.header("설정")

    st.session_state.mode = st.radio(
        "화면",
        ["개발자 등록", "기업/프로젝트 등록", "매칭 추천", "저장된 매칭 조회"]
    )

    colA, colB = st.columns(2)
    with colA:
        if st.button("DB 스키마 적용"):
            db.init_db(SCHEMA_SQL)
            st.success("스키마 적용 완료")
    with colB:
        if st.button("대화 초기화"):
            st.session_state.chat_msgs = []
            st.rerun()

    st.divider()
    st.caption("팁) 먼저 DB 스키마 적용 → 개발자/프로젝트 등록 → 매칭 추천")

# ----------------------------
# 공용: 채팅 렌더링
# ----------------------------
def render_chat():
    for m in st.session_state.chat_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

def push_msg(role: str, content: str):
    st.session_state.chat_msgs.append({"role": role, "content": content})

def pretty_json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)

# ----------------------------
# 공용: 점수 UI
# ----------------------------
def score_bar(score: int):
    st.progress(score / 100.0)
    if score >= 85:
        st.success(f"적합도 {score}점 (강력 추천)")
    elif score >= 70:
        st.info(f"적합도 {score}점 (추천)")
    elif score >= 50:
        st.warning(f"적합도 {score}점 (조건 보완 필요)")
    else:
        st.error(f"적합도 {score}점 (비추천)")

# ----------------------------
# 메인
# ----------------------------
st.title("💬 LangChain + Streamlit 개발자-프로젝트 매칭 (SQLite)")

# 화면별 안내
if st.session_state.mode == "개발자 등록":
    st.subheader("👨‍💻 개발자 등록 (채팅 입력 → JSON 구조화 → DB 저장)")
    st.caption("예) 백엔드 개발자, Java 4년/Spring 3년/Oracle 3년, IntelliJ 사용…")

elif st.session_state.mode == "기업/프로젝트 등록":
    st.subheader("🏢 기업/프로젝트 등록 (채팅 입력 → JSON 구조화 → DB 저장)")
    st.caption("예) Java+Oracle 기반, 3년차 이상, Oracle 필수, 가중치 설정…")

elif st.session_state.mode == "매칭 추천":
    st.subheader("🤖 프로젝트 선택 → 개발자 TOP N 추천 + 점수바 + 상세 이유 + 저장")
    st.caption("추천은 룰 기반 점수(일관성) + 상세 이유(설명력)로 구성됩니다.")

else:
    st.subheader("📌 저장된 매칭(matches) 조회")

# 채팅 영역(등록 화면에서만 사용)
if st.session_state.mode in ["개발자 등록", "기업/프로젝트 등록"]:
    render_chat()
    user_text = st.chat_input("여기에 입력하세요")

    if user_text:
        push_msg("user", user_text)

        if st.session_state.mode == "개발자 등록":
            res = (DEV_PROMPT | llm).invoke({"input": user_text})
            try:
                data = json.loads(res.content)
                dev_id = db.create_developer(
                    name=data["name"],
                    role=data.get("role", "etc"),
                    total_career_years=float(data.get("total_career_years", 0)),
                    headline=data.get("headline"),
                )
                db.save_developer_skills(dev_id, data.get("skills", []))
                st.session_state.last_saved_dev_id = dev_id

                push_msg("assistant",
                         "✅ 개발자 프로필 저장 완료!\n\n"
                         f"- developer_id = `{dev_id}`\n\n"
                         "구조화 결과(JSON):\n```json\n" + pretty_json(data) + "\n```")
            except Exception:
                push_msg("assistant",
                         "❌ JSON 파싱 실패. 입력을 더 명확히 해주세요.\n\n"
                         "AI 원본 응답:\n```\n" + res.content + "\n```")

        else:  # 기업/프로젝트 등록
            res = (PROJECT_PROMPT | llm).invoke({"input": user_text})
            try:
                data = json.loads(res.content)

                company_id = db.create_company(data["company_name"], data.get("industry"))
                project_id = db.create_project(
                    company_id=company_id,
                    project_name=data["project_name"],
                    description=data.get("description", ""),
                    min_total_career=float(data.get("min_total_career", 0)),
                )

                reqs = []
                for r in data.get("requirements", []):
                    reqs.append({
                        "skill": r["skill"],
                        "type": r.get("type", "etc"),
                        "min_level": int(r.get("min_level", 3)),
                        "min_years": float(r.get("min_years", 0)),
                        "weight": int(r.get("weight", 1)),
                        "mandatory": 1 if bool(r.get("mandatory", True)) else 0,
                    })

                db.save_project_requirements(project_id, reqs)
                st.session_state.last_saved_project_id = project_id

                push_msg("assistant",
                         "✅ 프로젝트 저장 완료!\n\n"
                         f"- project_id = `{project_id}`\n\n"
                         "구조화 결과(JSON):\n```json\n" + pretty_json(data) + "\n```")
            except Exception:
                push_msg("assistant",
                         "❌ JSON 파싱 실패. 입력을 더 명확히 해주세요.\n\n"
                         "AI 원본 응답:\n```\n" + res.content + "\n```")

        st.rerun()

# ----------------------------
# 매칭 추천 화면
# ----------------------------

 

if st.session_state.mode == "매칭 추천":
    projects = db.list_open_projects()
    devs = db.list_developers()

    if not projects or not devs:
        st.info("먼저 개발자와 프로젝트를 등록하세요.")
    else:
        # Row → dict 변환
        projects = [dict(r) for r in db.list_open_projects()]
        proj = st.selectbox(
            "프로젝트 선택",
            options=projects,
            format_func=lambda r: f"[{r['project_id']}] {r['company_name']} - {r['project_name']}"
        )

        top_n = st.slider("추천 인원 수", 1, 20, 5)

        # requirements 로드
        req_rows = db.get_project_requirements(int(proj["project_id"]))
        reqs = [dict(r) for r in req_rows]

        project_dict = {"min_total_career": float(proj["min_total_career"])}

        st.markdown("### 요구 기술")
        if reqs:
            st.dataframe(
                [{
                    "skill": r["skill_name"],
                    "min_level": r["min_skill_level"],
                    "min_years": r["min_experience_years"],
                    "weight": r["weight"],
                    "mandatory": "Y" if r["is_mandatory"] == 1 else "N"
                } for r in reqs],
                use_container_width=True
            )
        else:
            st.warning("요구 기술이 등록되지 않았습니다. (project_requirements가 비어있음)")

        st.divider()
        st.markdown("### 추천 결과")

        results = []
        for d in devs:
            dev_id = int(d["developer_id"])
            dev_skill_rows = db.get_developer_skills(dev_id)
            dev_skills = [dict(s) for s in dev_skill_rows]

            dev_dict = {
                "total_career_years": float(d["total_career_years"]),
                "role": d["role"],
            }

            score, reason = calc_match_score(dev_dict, project_dict, dev_skills, reqs)
            if score > 0:
                results.append((score, dev_id, d["name"], d["role"], reason, dev_skills))

        results.sort(key=lambda x: x[0], reverse=True)
        results = results[:top_n]

        if not results:
            st.warning("필수 조건을 만족하는 개발자가 없습니다.")
        else:
            for score, dev_id, name, role, reason, dev_skills in results:
                with st.container(border=True):
                    st.markdown(f"#### ✅ {name} ({role}) — **{score}점**")
                    score_bar(score)

                    with st.expander("매칭 상세 이유"):
                        st.text(reason)

                    with st.expander("개발자 기술 목록"):
                        st.dataframe(
                            [{
                                "skill": s["skill_name"],
                                "level": s["skill_level"],
                                "years": s["experience_years"],
                                "primary": "Y" if s["is_primary"] == 1 else "N"
                            } for s in dev_skills],
                            use_container_width=True
                        )

                    if st.button(f"💾 matches에 저장 (dev_id={dev_id})", key=f"save_{proj['project_id']}_{dev_id}"):
                        db.save_match(int(proj["project_id"]), dev_id, score, reason)
                        st.success("저장 완료!")

# ----------------------------
# 저장된 매칭 조회 화면
# ----------------------------
if st.session_state.mode == "저장된 매칭 조회":
    rows = db.list_matches()
    if not rows:
        st.info("저장된 매칭이 없습니다. (매칭 추천 화면에서 저장해보세요)")
    else:
        st.dataframe(
            [{
                "match_id": r["match_id"],
                "project_id": r["project_id"],
                "project_name": r["project_name"],
                "company": r["company_name"],
                "developer_id": r["developer_id"],
                "developer_name": r["developer_name"],
                "score": r["match_score"],
                "created_at": r["created_at"],
            } for r in rows],
            use_container_width=True
        )

        with st.expander("선택한 매칭 reason 보기"):
            match_id = st.selectbox("match_id", [r["match_id"] for r in rows])
            detail = db.get_match_detail(int(match_id))
            st.text(detail["reason"])