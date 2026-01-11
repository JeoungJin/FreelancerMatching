from typing import Dict, List, Tuple

def calc_match_score(
    dev: Dict,
    project: Dict,
    dev_skills: List[Dict],
    reqs: List[Dict],
) -> Tuple[int, str]:
    """
    dev: {"total_career_years":..., "role":...}
    project: {"min_total_career":...}
    dev_skills: [{"skill_name":..., "skill_level":..., "experience_years":...}, ...]
    reqs: [{"skill_name":..., "min_skill_level":..., "min_experience_years":..., "weight":..., "is_mandatory":...}, ...]
    """
    # 1) 전체 경력 필터
    if float(dev["total_career_years"]) < float(project["min_total_career"]):
        return 0, "전체 경력이 최소 요구 경력보다 낮습니다."

    dev_map = {s["skill_name"].lower(): s for s in dev_skills}

    # 2) 필수 조건 체크
    for r in reqs:
        if int(r["is_mandatory"]) == 1:
            key = r["skill_name"].lower()
            if key not in dev_map:
                return 0, f"필수 기술({r['skill_name']})이 없습니다."

            s = dev_map[key]
            if int(s["skill_level"]) < int(r["min_skill_level"]):
                return 0, f"필수 기술({r['skill_name']}) 숙련도 부족."
            if float(s["experience_years"]) < float(r["min_experience_years"]):
                return 0, f"필수 기술({r['skill_name']}) 사용 연차 부족."

    # 3) 점수 계산 (레벨 + 연차)
    score = 0.0
    max_score = 0.0
    reasons = []

    for r in reqs:
        weight = float(r["weight"])
        max_score += weight * 2.0  # level + years

        key = r["skill_name"].lower()
        if key not in dev_map:
            if int(r["is_mandatory"]) == 1:
                # 여기까지 오면 필수는 모두 존재하므로 실질적으로는 안 걸림
                continue
            else:
                reasons.append(f"- {r['skill_name']}: 보유하지 않음(선택)")
                continue

        s = dev_map[key]

        # level 충족률 (0~1)
        level_ratio = min(float(s["skill_level"]) / float(r["min_skill_level"]), 1.0) if float(r["min_skill_level"]) > 0 else 1.0
        # years 충족률 (0~1)
        years_ratio = min(float(s["experience_years"]) / float(r["min_experience_years"]), 1.0) if float(r["min_experience_years"]) > 0 else 1.0

        part = (level_ratio + years_ratio) * weight
        score += part

        reasons.append(
            f"- {r['skill_name']}: 레벨 {s['skill_level']}/{r['min_skill_level']}({level_ratio:.2f}), "
            f"연차 {s['experience_years']}/{r['min_experience_years']}({years_ratio:.2f}), "
            f"가중치 {int(r['weight'])}"
        )

    final = int(round((score / max_score) * 100)) if max_score > 0 else 0
    reason_text = "기술 매칭 상세:\n" + "\n".join(reasons)
    return final, reason_text