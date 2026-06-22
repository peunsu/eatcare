"""현재 스키마 ERD(SVG 2종) — Graphviz로 '좌표만' 계산하고, 렌더링은 앱 디자인(파랑/Pretendard)으로 직접.
레이아웃 엔진이 배치·라우팅을 처리하므로 겹침이 없고, 출력 SVG는 DOCTYPE 없이 px 단위라 어디서나 렌더된다.

서버(graphviz 설치 필요)에서 실행:  python scripts/gen_erd.py
"""
import os
import subprocess

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documents")
DOT, NEATO = "/usr/bin/dot", "/usr/bin/neato"
FONT = "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"
SX = 72.0  # inch → px

# ===== 스키마 =====
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
REL = [("MEMBER","MEMBER_DISEASE"),("DISEASE","MEMBER_DISEASE"),("NUTRIENT","DISEASE"),
       ("FOOD","FOOD_NUTRIENT"),("NUTRIENT","FOOD_NUTRIENT"),("MEMBER","DIET_RECORD"),
       ("FOOD","DIET_RECORD"),("MEMBER","DAILY_SUMMARY"),("DAILY_SUMMARY","SUMMARY_NUTRIENT"),
       ("NUTRIENT","SUMMARY_NUTRIENT"),("DAILY_SUMMARY","NOTIFICATION")]
TAGCOL = {"PK":"#1b64da","PK,FK":"#1b64da","FK":"#94a3b8","UK":"#0891b2","GEN":"#9333ea"}
BOXW, HDR, ROWH = 270, 34, 24


def table_size(name):
    return BOXW, HDR + len(TABLES[name][1]) * ROWH


def run_plain(engine, dot):
    return subprocess.run([engine, "-Tplain"], input=dot, capture_output=True, text=True, check=True).stdout


def parse_plain(text):
    nodes, edges, gh = {}, [], 0.0
    for ln in text.splitlines():
        t = ln.split()
        if not t:
            continue
        if t[0] == "graph":
            gh = float(t[3])
        elif t[0] == "node":
            nodes[t[1]] = (float(t[2]), float(t[3]), float(t[4]), float(t[5]))
        elif t[0] == "edge":
            n = int(t[3]); pts = [(float(t[4 + 2*i]), float(t[5 + 2*i])) for i in range(n)]
            edges.append((t[1], t[2], pts))
    # y축 뒤집어 px 좌표로
    P = lambda x, y: (x * SX, (gh - y) * SX)
    N = {k: (P(x, y), w * SX, h * SX) for k, (x, y, w, h) in nodes.items()}
    E = [(a, b, [P(x, y) for x, y in pts]) for a, b, pts in edges]
    return N, E, gh * SX


def _u(a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    d = (dx*dx + dy*dy) ** 0.5 or 1
    return dx/d, dy/d


def crow(p_into, p_from):  # 까마귀발(N) at p_into
    ux, uy = _u(p_into, p_from); bx, by = p_into[0]+ux*16, p_into[1]+uy*16; nx, ny = -uy, ux
    return "".join(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{p_into[0]+nx*9*k:.1f}" y2="{p_into[1]+ny*9*k:.1f}" stroke="#334155" stroke-width="1.6"/>' for k in (-1,0,1))


def tee(p_at, p_to):  # 단일막대(1) at p_at
    ux, uy = _u(p_at, p_to); mx, my = p_at[0]+ux*13, p_at[1]+uy*13; nx, ny = -uy, ux
    return f'<line x1="{mx+nx*10:.1f}" y1="{my+ny*10:.1f}" x2="{mx-nx*10:.1f}" y2="{my-ny*10:.1f}" stroke="#334155" stroke-width="1.9"/>'


# ===================== IE =====================
def build_ie_dot():
    L = ['digraph G {', '  graph [rankdir=LR, splines=ortho, nodesep=0.55, ranksep=1.1];', '  node [shape=box, fixedsize=true];']
    for name in TABLES:
        w, h = table_size(name)
        L.append(f'  {name} [width={w/SX:.3f}, height={h/SX:.3f}, label=""];')
    for p, c in REL:
        L.append(f'  {p} -> {c};')
    L.append("}")
    return "\n".join(L)


def render_ie():
    N, E, H = parse_plain(run_plain(DOT, build_ie_dot()))
    W = max(c[0][0] + c[1]/2 for c in N.values()) + 40
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H+90:.0f}" font-family="{FONT}">',
         f'<rect width="{W:.0f}" height="{H+90:.0f}" fill="#ffffff"/>',
         '<text x="36" y="44" font-size="23" font-weight="800" fill="#0f172a">EatCare 시스템 ERD — IE(까마귀발) 표기법</text>',
         '<text x="36" y="68" font-size="12.5" fill="#64748b">┃=1(부모) · 까마귀발=N(자식) · PK(밑줄) · FK · UK · GEN(생성컬럼) · 회색=데이터 타입</text>',
         '<g transform="translate(0,84)">']
    for a, b, pts in E:  # 관계선(박스 아래)
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        s.append(f'<path d="{d}" fill="none" stroke="#64748b" stroke-width="1.4"/>')
        s.append(crow(pts[-1], pts[-2]))   # head=자식(N)
        s.append(tee(pts[0], pts[1]))      # tail=부모(1)
    for name, ((cx, cy), w, h) in N.items():
        x, y = cx - w/2, cy - h/2
        title, attrs = TABLES[name]
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="#ffffff" stroke="#1b64da" stroke-width="1.6"/>')
        s.append(f'<path d="M{x+10:.1f} {y:.1f} H{x+w-10:.1f} A10 10 0 0 1 {x+w:.1f} {y+10:.1f} V{y+HDR:.1f} H{x:.1f} V{y+10:.1f} A10 10 0 0 1 {x+10:.1f} {y:.1f} Z" fill="#3182f6"/>')
        s.append(f'<text x="{x+12:.1f}" y="{y+22:.1f}" font-size="13" font-weight="700" fill="#fff">{title}</text>')
        for i, (nm, ty, tag) in enumerate(attrs):
            ry = y + HDR + ROWH*i; by = ry + 16
            if i:
                s.append(f'<line x1="{x:.1f}" y1="{ry:.1f}" x2="{x+w:.1f}" y2="{ry:.1f}" stroke="#eef2f7"/>')
            pk = "PK" in tag; deco = ' text-decoration="underline"' if pk else ""
            s.append(f'<text x="{x+12:.1f}" y="{by:.1f}" font-size="12" font-weight="{"700" if pk else "500"}" fill="#0f172a"{deco}>{nm}</text>')
            s.append(f'<text x="{x+118:.1f}" y="{by:.1f}" font-size="10" fill="#64748b">{ty}</text>')
            if tag:
                s.append(f'<text x="{x+w-11:.1f}" y="{by:.1f}" font-size="9.5" text-anchor="end" font-weight="700" fill="{TAGCOL.get(tag,"#94a3b8")}">{tag}</text>')
    s.append("</g></svg>")
    return "".join(s)


# ===================== Chen =====================
CHEN_ATTR = {
    "MEMBER": ["회원코드*","이름","출생년도","성별","이메일","비밀번호","가입일","역할","계정상태"],
    "DIET_RECORD": ["기록코드*","섭취량","기록일시"],
    "FOOD": ["식품코드*","식품명","기준량","기준단위","대분류","검색명"],
    "NOTIFICATION": ["알림코드*","알림유형","알림내용","발송일시","읽음여부"],
    "NUTRIENT": ["영양소코드*","영양소명","단위"],
    "DISEASE": ["질환코드*","질환명","일일상한값"],
    "DAILY_SUMMARY": ["요약코드*","날짜","위험도"],
}
CHEN_E = list(CHEN_ATTR)
CHEN_R = [("함유","FOOD","M","NUTRIENT","N","함량"),("기준","DISEASE","N","NUTRIENT","1",None),
          ("집계","DAILY_SUMMARY","M","NUTRIENT","N","누적량"),("보유","MEMBER","M","DISEASE","N","등록일"),
          ("기록","MEMBER","1","DIET_RECORD","N",None),("참조","DIET_RECORD","N","FOOD","1",None),
          ("생성","MEMBER","1","DAILY_SUMMARY","N",None),("발생","DAILY_SUMMARY","1","NOTIFICATION","N",None)]


def _tw(s):  # 대략적 텍스트 폭(px)
    return sum(13 if ord(c) > 127 else 7.3 for c in s)


def build_chen_dot():
    L = ['graph G {', '  graph [layout=neato, overlap=false, splines=true, sep="+22"];', '  node [fixedsize=true];']
    for e in CHEN_E:
        w = max(_tw(e) + 34, 150)
        L.append(f'  {e} [shape=box, width={w/SX:.3f}, height={56/SX:.3f}, label=""];')
        for i, a in enumerate(CHEN_ATTR[e]):
            nm = a[:-1] if a.endswith("*") else a
            aw = max(_tw(nm) + 26, 60)
            L.append(f'  A_{e}_{i} [shape=ellipse, width={aw/SX:.3f}, height={34/SX:.3f}, label=""];')
            L.append(f'  {e} -- A_{e}_{i};')
    for idx, (lab, A, cA, B, cB, ra) in enumerate(CHEN_R):
        L.append(f'  R{idx} [shape=diamond, width={max(_tw(lab)+44,96)/SX:.3f}, height={66/SX:.3f}, label=""];')
        L.append(f'  {A} -- R{idx};')
        L.append(f'  R{idx} -- {B};')
        if ra:
            aw = max(_tw(ra) + 26, 60)
            L.append(f'  RA{idx} [shape=ellipse, width={aw/SX:.3f}, height={34/SX:.3f}, label=""];')
            L.append(f'  R{idx} -- RA{idx};')
    L.append("}")
    return "\n".join(L)


def render_chen():
    N, E, H = parse_plain(run_plain(NEATO, build_chen_dot()))
    W = max(c[0][0] + c[1]/2 for c in N.values()) + 50
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H+90:.0f}" font-family="{FONT}">',
         f'<rect width="{W:.0f}" height="{H+90:.0f}" fill="#ffffff"/>',
         '<text x="40" y="46" font-size="26" font-weight="800" fill="#0f172a">EatCare 시스템 ERD — 피터 첸(Chen) 표기법</text>',
         '<text x="40" y="72" font-size="13" fill="#64748b">사각형=개체 · 마름모=관계 · 타원=속성(밑줄=PK) · 1·M·N=카디널리티 · M:N은 관계+속성</text>',
         '<g transform="translate(0,84)">']
    # 간선
    for a, b, pts in E:
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        if a.startswith("A_") or b.startswith("A_"):
            s.append(f'<path d="{d}" fill="none" stroke="#c7d2e0" stroke-width="1.1"/>')
        elif a.startswith("RA") or b.startswith("RA"):
            s.append(f'<path d="{d}" fill="none" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="5 4"/>')
        else:
            s.append(f'<path d="{d}" fill="none" stroke="#475569" stroke-width="1.5"/>')
    # 속성 타원
    for e in CHEN_E:
        for i, a in enumerate(CHEN_ATTR[e]):
            pk = a.endswith("*"); nm = a[:-1] if pk else a
            (cx, cy), w, h = N[f"A_{e}_{i}"]
            s.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" fill="#ffffff" stroke="#3182f6" stroke-width="1.3"/>')
            deco = ' text-decoration="underline"' if pk else ""
            s.append(f'<text x="{cx:.1f}" y="{cy+4:.1f}" font-size="12" text-anchor="middle" fill="#0f172a" font-weight="{"700" if pk else "500"}"{deco}>{nm}</text>')
    for idx, (lab, A, cA, B, cB, ra) in enumerate(CHEN_R):
        if ra:
            (cx, cy), w, h = N[f"RA{idx}"]
            s.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" fill="#f1f5f9" stroke="#94a3b8" stroke-width="1.2"/>')
            s.append(f'<text x="{cx:.1f}" y="{cy+4:.1f}" font-size="12" text-anchor="middle" fill="#334155">{ra}</text>')
    # 마름모
    for idx, (lab, *_rest) in enumerate(CHEN_R):
        (cx, cy), w, h = N[f"R{idx}"]
        s.append(f'<path d="M{cx:.1f} {cy-h/2:.1f} L{cx+w/2:.1f} {cy:.1f} L{cx:.1f} {cy+h/2:.1f} L{cx-w/2:.1f} {cy:.1f} Z" fill="#fff7ed" stroke="#ea7317" stroke-width="1.7"/>')
        s.append(f'<text x="{cx:.1f}" y="{cy+5:.1f}" font-size="14" font-weight="700" text-anchor="middle" fill="#9a3412">{lab}</text>')
    # 개체
    for e in CHEN_E:
        (cx, cy), w, h = N[e]
        s.append(f'<rect x="{cx-w/2:.1f}" y="{cy-h/2:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="#eff6ff" stroke="#1b64da" stroke-width="2.2"/>')
        s.append(f'<text x="{cx:.1f}" y="{cy+6:.1f}" font-size="16" font-weight="800" text-anchor="middle" fill="#0f172a">{e}</text>')
    # 카디널리티(개체-관계 직선상, 개체 쪽)
    for idx, (lab, A, cA, B, cB, ra) in enumerate(CHEN_R):
        rc = N[f"R{idx}"][0]
        for ent, card in ((A, cA), (B, cB)):
            ec = N[ent][0]
            lx, ly = ec[0] + (rc[0]-ec[0])*0.34, ec[1] + (rc[1]-ec[1])*0.34
            s.append(f'<rect x="{lx-10:.1f}" y="{ly-12:.1f}" width="20" height="18" rx="4" fill="#ffffff" opacity="0.92"/>')
            s.append(f'<text x="{lx:.1f}" y="{ly+2:.1f}" font-size="15" font-weight="800" text-anchor="middle" fill="#1b64da">{card}</text>')
    s.append("</g></svg>")
    return "".join(s)


def main():
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "nutrition_erd.svg"), "w", encoding="utf-8").write(render_ie())
    open(os.path.join(OUT, "nutrition_erd_chen.svg"), "w", encoding="utf-8").write(render_chen())
    print("생성 완료: nutrition_erd.svg, nutrition_erd_chen.svg")


if __name__ == "__main__":
    main()
