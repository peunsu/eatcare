"""현재 스키마 → Graphviz DOT 2종 생성(레이아웃은 dot/neato가 처리).
 - nutrition_erd.dot       : IE(까마귀발) — dot 엔진, HTML 테이블 + crow/tee 화살표
 - nutrition_erd_chen.dot  : 첸 — neato 엔진, 개체(박스)+관계(마름모)+속성(타원)
실행 후 서버에서:
   dot   -Tsvg nutrition_erd.dot      -o nutrition_erd.svg
   neato -Tsvg nutrition_erd_chen.dot -o nutrition_erd_chen.svg
"""
import os
FONT = "NanumGothic"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documents")

# ---- 공통 스키마 (이름, 타입, tag) ----
TABLES = {
    "MEMBER": ("MEMBER · 회원", [("회원코드","INT","PK"),("이름","VARCHAR(50)",""),("출생년도","INT",""),("성별","ENUM(M,F)",""),("이메일","VARCHAR(255)","UK"),("비밀번호","VARCHAR(255)",""),("가입일","DATE",""),("역할","ENUM",""),("계정상태","ENUM","")]),
    "DIET_RECORD": ("DIET_RECORD · 식단기록", [("기록코드","INT","PK"),("회원코드","INT","FK"),("식품코드","VARCHAR(32)","FK"),("섭취량","FLOAT",""),("기록일시","DATETIME","")]),
    "FOOD": ("FOOD · 식품", [("식품코드","VARCHAR(32)","PK"),("식품명","VARCHAR(255)",""),("기준량","FLOAT",""),("기준단위","VARCHAR(20)",""),("대분류","VARCHAR(50)",""),("검색명","VARCHAR(255)","GEN")]),
    "MEMBER_DISEASE": ("MEMBER_DISEASE · 회원·질환", [("회원코드","INT","PK,FK"),("질환코드","INT","PK,FK"),("등록일","DATE","")]),
    "DAILY_SUMMARY": ("DAILY_SUMMARY · 일일요약", [("요약코드","INT","PK"),("회원코드","INT","FK"),("날짜","DATE",""),("위험도","ENUM","")]),
    "FOOD_NUTRIENT": ("FOOD_NUTRIENT · 식품·영양소", [("식품코드","VARCHAR(32)","PK,FK"),("영양소코드","INT","PK,FK"),("함량","FLOAT","")]),
    "NOTIFICATION": ("NOTIFICATION · 알림", [("알림코드","INT","PK"),("요약코드","INT","FK"),("알림유형","ENUM",""),("알림내용","VARCHAR(255)",""),("발송일시","DATETIME",""),("읽음여부","BOOLEAN","")]),
    "DISEASE": ("DISEASE · 질환", [("질환코드","INT","PK"),("질환명","VARCHAR(50)",""),("영양소코드","INT","FK"),("일일상한값","FLOAT","")]),
    "NUTRIENT": ("NUTRIENT · 영양소", [("영양소코드","INT","PK"),("영양소명","VARCHAR(50)",""),("단위","VARCHAR(20)","")]),
    "SUMMARY_NUTRIENT": ("SUMMARY_NUTRIENT · 요약·영양소", [("요약코드","INT","PK,FK"),("영양소코드","INT","PK,FK"),("누적량","FLOAT","")]),
}
REL = [  # (부모=1, 자식=N)
    ("MEMBER","MEMBER_DISEASE"),("DISEASE","MEMBER_DISEASE"),("NUTRIENT","DISEASE"),
    ("FOOD","FOOD_NUTRIENT"),("NUTRIENT","FOOD_NUTRIENT"),
    ("MEMBER","DIET_RECORD"),("FOOD","DIET_RECORD"),
    ("MEMBER","DAILY_SUMMARY"),("DAILY_SUMMARY","SUMMARY_NUTRIENT"),("NUTRIENT","SUMMARY_NUTRIENT"),
    ("DAILY_SUMMARY","NOTIFICATION"),
]
TAGCOL = {"PK":"#1b64da","PK,FK":"#1b64da","FK":"#94a3b8","UK":"#0891b2","GEN":"#9333ea"}


def ie_label(name):
    title, attrs = TABLES[name]
    rows = [f'<TR><TD BGCOLOR="#3182f6" COLSPAN="3"><FONT COLOR="#ffffff" POINT-SIZE="12"><B>{title}</B></FONT></TD></TR>']
    for nm, ty, tag in attrs:
        cell = f'<U>{nm}</U>' if "PK" in tag else nm
        tg = f'<FONT COLOR="{TAGCOL.get(tag,"#94a3b8")}" POINT-SIZE="9"><B>{tag}</B></FONT>' if tag else ""
        rows.append(
            f'<TR><TD ALIGN="LEFT" PORT="{nm}">{cell}</TD>'
            f'<TD ALIGN="LEFT"><FONT COLOR="#64748b" POINT-SIZE="10">{ty}</FONT></TD>'
            f'<TD ALIGN="LEFT">{tg}</TD></TR>')
    return ('<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="5">'
            + "".join(rows) + "</TABLE>>")


def build_ie_dot():
    L = ['digraph ERD {',
         f'  graph [rankdir=LR, splines=ortho, nodesep=0.45, ranksep=1.05, bgcolor="white", fontname="{FONT}"];',
         f'  node  [shape=plaintext, fontname="{FONT}"];',
         '  edge  [dir=both, arrowhead=crow, arrowtail=tee, color="#475569", penwidth=1.3];']
    for name in TABLES:
        L.append(f'  {name} [label={ie_label(name)}];')
    for p, c in REL:
        L.append(f'  {p} -> {c};')
    L.append("}")
    return "\n".join(L)


# ---- Chen ----
CHEN_E = ["MEMBER","DIET_RECORD","FOOD","NOTIFICATION","NUTRIENT","DISEASE","DAILY_SUMMARY"]
CHEN_ATTR = {  # '*'=PK
    "MEMBER": ["회원코드*","이름","출생년도","성별","이메일","비밀번호","가입일","역할","계정상태"],
    "DIET_RECORD": ["기록코드*","섭취량","기록일시"],
    "FOOD": ["식품코드*","식품명","기준량","기준단위","대분류","검색명"],
    "NOTIFICATION": ["알림코드*","알림유형","알림내용","발송일시","읽음여부"],
    "NUTRIENT": ["영양소코드*","영양소명","단위"],
    "DISEASE": ["질환코드*","질환명","일일상한값"],
    "DAILY_SUMMARY": ["요약코드*","날짜","위험도"],
}
CHEN_R = [  # (라벨, A, cardA, B, cardB, 관계속성|None)
    ("함유","FOOD","M","NUTRIENT","N","함량"),
    ("기준","DISEASE","N","NUTRIENT","1",None),
    ("집계","DAILY_SUMMARY","M","NUTRIENT","N","누적량"),
    ("보유","MEMBER","M","DISEASE","N","등록일"),
    ("기록","MEMBER","1","DIET_RECORD","N",None),
    ("참조","DIET_RECORD","N","FOOD","1",None),
    ("생성","MEMBER","1","DAILY_SUMMARY","N",None),
    ("발생","DAILY_SUMMARY","1","NOTIFICATION","N",None),
]


def build_chen_dot():
    L = ['graph CHEN {',
         f'  layout=neato; overlap=false; splines=true; sep="+18"; bgcolor="white"; fontname="{FONT}"; fontsize=11;',
         f'  node [fontname="{FONT}"];',
         f'  edge [fontname="{FONT}", color="#64748b", penwidth=1.2];']
    # 개체
    for e in CHEN_E:
        L.append(f'  {e} [shape=box, style="filled,bold", fillcolor="#eff6ff", color="#1b64da", penwidth=2, fontsize=16, margin="0.18,0.10", label="{e}"];')
    # 속성
    for e in CHEN_E:
        for i, a in enumerate(CHEN_ATTR[e]):
            pk = a.endswith("*"); nm = a[:-1] if pk else a
            lab = f'<<U>{nm}</U>>' if pk else f'"{nm}"'
            L.append(f'  A_{e}_{i} [shape=ellipse, color="#3182f6", fontsize=12, width=0.1, height=0.1, label={lab}];')
            L.append(f'  {e} -- A_{e}_{i} [color="#c7d2e0", penwidth=1.0];')
    # 관계(마름모) + 카디널리티 + 관계속성
    for idx, (lab, A, cA, B, cB, ra) in enumerate(CHEN_R):
        rid = f'R{idx}'
        L.append(f'  {rid} [shape=diamond, style=filled, fillcolor="#fff7ed", color="#ea7317", penwidth=1.6, fontsize=13, label="{lab}"];')
        L.append(f'  {A} -- {rid} [taillabel="{cA}", labeldistance=1.9, labelangle=18, fontsize=15, fontcolor="#1b64da"];')
        L.append(f'  {rid} -- {B} [headlabel="{cB}", labeldistance=1.9, labelangle=18, fontsize=15, fontcolor="#1b64da"];')
        if ra:
            L.append(f'  RA{idx} [shape=ellipse, color="#94a3b8", style=dashed, fontsize=12, label="{ra}"];')
            L.append(f'  {rid} -- RA{idx} [style=dashed, color="#94a3b8"];')
    L.append("}")
    return "\n".join(L)


def main():
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "nutrition_erd.dot"), "w", encoding="utf-8").write(build_ie_dot())
    open(os.path.join(OUT, "nutrition_erd_chen.dot"), "w", encoding="utf-8").write(build_chen_dot())
    print("DOT 생성: nutrition_erd.dot, nutrition_erd_chen.dot")


if __name__ == "__main__":
    main()
