#!/usr/bin/env bash
# API E2E smoke test (서버 내부에서 curl)
set -e
B=http://localhost:8000
EMAIL="smoke_$(date +%s)@test.local"
echo "== signup =="
TOK=$(curl -s -X POST $B/api/auth/signup -H 'Content-Type: application/json' \
  -d "{\"name\":\"스모크\",\"email\":\"$EMAIL\",\"password\":\"pass1234\",\"birth_year\":1980,\"gender\":\"F\"}" \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
echo "token: ${TOK:0:20}..."
H="Authorization: Bearer $TOK"

echo "== me =="
curl -s $B/api/members/me -H "$H"; echo

echo "== disease catalog =="
curl -s $B/api/members/diseases -H "$H"; echo

echo "== add 당뇨(1) + 고혈압(2) =="
curl -s -X POST $B/api/members/me/diseases -H "$H" -H 'Content-Type: application/json' -d '{"disease_code":1}' >/dev/null
curl -s -X POST $B/api/members/me/diseases -H "$H" -H 'Content-Type: application/json' -d '{"disease_code":2}'; echo

echo "== add diet record (식품 D202-120000000-1180, 1000g) =="
curl -s -X POST $B/api/diet/records -H "$H" -H 'Content-Type: application/json' \
  -d '{"food_code":"D202-120000000-1180","amount":1000}'; echo

echo "== daily report =="
curl -s "$B/api/reports/daily" -H "$H"; echo

echo "== notifications =="
curl -s $B/api/notifications -H "$H"; echo

echo "== admin login + report =="
ATOK=$(curl -s -X POST $B/api/auth/login -d 'username=admin@nutrition.local&password=admin1234' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s "$B/api/admin/report?age_min=40&age_max=59&gender=F&disease_code=2" -H "Authorization: Bearer $ATOK"; echo
echo "DONE"
