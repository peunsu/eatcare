// 공통 API 헬퍼
const TOKEN_KEY = "nutri_token";
const ROLE_KEY = "nutri_role";
const THEME_KEY = "nutri_theme";

// ===== 다크모드 =====
function currentTheme() { return document.documentElement.getAttribute("data-theme") || "light"; }
function setThemeAttr(t) {
  const e = document.documentElement;
  e.setAttribute("data-theme", t);       // 커스텀 토스 토큰
  e.setAttribute("data-bs-theme", t);    // Bootstrap 컴포넌트(표/텍스트/아이콘)
}
function applyTheme() {
  setThemeAttr(localStorage.getItem(THEME_KEY) || "light");
  updateThemeBtn();
}
function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  setThemeAttr(next);
  updateThemeBtn();
  if (window.onThemeChange) window.onThemeChange();
}
function updateThemeBtn() {
  const b = document.getElementById("themeBtn");
  if (b) b.textContent = currentTheme() === "dark" ? "☀️" : "🌙";
}

function setAuth(token, role) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
}
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function getRole() { return localStorage.getItem(ROLE_KEY); }
function clearAuth() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(ROLE_KEY); }
function requireAuth() { if (!getToken()) location.href = "/index.html"; }
function logout() { clearAuth(); location.href = "/index.html"; }

// JSON API 호출
async function api(path, { method = "GET", body = null } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  if (body !== null) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: body !== null ? JSON.stringify(body) : null });
  if (res.status === 401) { clearAuth(); location.href = "/index.html"; throw new Error("unauthorized"); }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error(detailOf(data));
  return data;
}

// 로그인(form-urlencoded)
async function login(email, password) {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(detailOf(data));
  return data;
}

function detailOf(data) {
  if (typeof data === "string") return data;
  if (data && data.detail) {
    if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join(", ");
    return data.detail;
  }
  return "오류가 발생했습니다.";
}

const RISK_CLASS = { "정상": "success", "주의": "warning", "위험": "danger", "경고": "danger-strong" };

// 질환별 색상 태그
const DISEASE_COLORS = { "당뇨": "#3182f6", "고혈압": "#ff9e2c", "고지혈증": "#8b5cf6" };
function diseaseBadge(name) {
  const c = DISEASE_COLORS[name] || "#64748b";
  return `<span class="badge me-1" style="background:${c};color:#fff">${name}</span>`;
}

// 알림 유형(영문 enum) → 한국어 배지
const NOTI_KO = { WARNING: ["주의", "warning"], DANGER: ["위험", "danger"], CRITICAL: ["경고", "danger-strong"] };
function notiBadge(type) {
  const [ko, cls] = NOTI_KO[type] || [type, "secondary"];
  return `<span class="badge bg-${cls}">${ko}</span>`;
}
function notiText(content) { return (content || "").replace(/^\[[^\]]*\]\s*/, ""); }

// 차트 기준선 라벨을 뒤 배경과 겹치지 않게 "알약" 배경 위에 그림.
// align "right": x=오른쪽 끝, "left": x=왼쪽 끝, "center": x=가로 중앙. (y=세로 중앙)
// maxRight 가 주어지면 알약이 그 좌표를 넘지 않도록 보정.
function drawChartTag(ctx, label, x, y, align, maxRight) {
  ctx.save();
  ctx.font = "700 11px Pretendard, sans-serif";
  const tw = ctx.measureText(label).width;
  const padX = 6, h = 17, w = tw + padX * 2, r = 5;
  let left = align === "right" ? x - w : (align === "center" ? x - w / 2 : x);
  left = Math.max(2, left);
  if (maxRight) left = Math.min(left, maxRight - w - 2);
  const top = y - h / 2;
  ctx.beginPath();
  ctx.moveTo(left + r, top);
  ctx.arcTo(left + w, top, left + w, top + h, r);
  ctx.arcTo(left + w, top + h, left, top + h, r);
  ctx.arcTo(left, top + h, left, top, r);
  ctx.arcTo(left, top, left + w, top, r);
  ctx.closePath();
  ctx.fillStyle = currentTheme() === "dark" ? "#2b2f36" : "#ffffff";
  ctx.globalAlpha = 0.95; ctx.fill(); ctx.globalAlpha = 1;
  ctx.lineWidth = 1; ctx.strokeStyle = "#f04452"; ctx.stroke();
  ctx.fillStyle = "#f04452"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  ctx.fillText(label, left + padX, top + h / 2 + 0.5);
  ctx.restore();
}

// 차트 가로 점선 기준선 (plugins.hLine.value 가 있을 때만)
const HLINE_PLUGIN = {
  id: "hLine",
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || opts.value == null) return;
    const y = chart.scales.y;
    if (!y) return;
    const py = y.getPixelForValue(opts.value);
    const { ctx, chartArea } = chart;
    if (py < chartArea.top || py > chartArea.bottom) return;
    ctx.save();
    ctx.beginPath();
    ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.strokeStyle = "#f04452";
    ctx.moveTo(chartArea.left, py); ctx.lineTo(chartArea.right, py); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
    // 상한값(예: 100)에 해당하는 좌측 y축 눈금 숫자에 빨간 테두리 강조
    const ty = Math.min(Math.max(py, 10), chart.height - 10);
    drawChartTag(ctx, String(opts.value), chartArea.left - 3, ty, "right");
  },
};

// 공통 플로팅 호버 툴팁 — data-tip 요소 위에서 마우스를 따라 표시
function initTooltips() {
  let tip = null, curEl = null;
  const ensure = () => { if (!tip) { tip = document.createElement("div"); tip.className = "app-tip"; document.body.appendChild(tip); } return tip; };
  const place = (x, y) => {
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = x + 14, top = y + 16;
    if (left + tw > window.innerWidth - 8) left = x - tw - 14;
    if (top + th > window.innerHeight - 8) top = y - th - 16;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.max(8, top) + "px";
  };
  const hide = () => { curEl = null; if (tip) { tip.style.opacity = "0"; tip.style.display = "none"; } };
  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest("[data-tip]");
    if (!el) { if (curEl) hide(); return; }
    const t = ensure();
    if (el !== curEl) { curEl = el; t.textContent = el.getAttribute("data-tip"); t.style.display = "block"; t.style.opacity = "1"; }
    place(e.clientX, e.clientY);
  });
  document.addEventListener("click", hide, true);
}

applyTheme();
initTooltips();
