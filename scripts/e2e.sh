#!/usr/bin/env bash
# End-to-end lifecycle check (Milestone 3.3): resume upload -> register -> 2FA -> profile -> dashboard.
# Needs the API running with DEBUG_RETURN_OTP=true (the OTP is returned in the register response).
#   BASE=http://localhost:8000 bash scripts/e2e.sh
set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SAMPLE="$HERE/sample_resume.docx"
[ -f "$SAMPLE" ] || python3 "$HERE/make_sample_resume.py" "$SAMPLE"

jget() { python3 -c "import sys, json; print(json.load(sys.stdin)$1)"; }
step() { printf '\n== %s\n' "$1"; }
json_post() { curl -sS -X POST -H 'Content-Type: application/json' -d "$2" "$1"; }

step "1. Upload resume and parse"
PARSE=$(curl -sS -f -F "file=@$SAMPLE" "$BASE/api/v1/resume/parse")
echo "$PARSE" | python3 -m json.tool
RESUME_ID=$(echo "$PARSE" | jget "['resume_id']")

step "2. Register (frontend autofills from the parsed JSON; email made unique for reruns)"
EMAIL="intern.$(date +%s)@example.com"
BODY=$(PARSE="$PARSE" EMAIL="$EMAIL" python3 - <<'PY'
import json, os
p = json.loads(os.environ["PARSE"])
parsed = p["parsed"]
print(json.dumps({
    "full_name": parsed.get("name") or "Test Intern",
    "email": os.environ["EMAIL"],
    "phone": parsed.get("phone") or "+919876543210",
    "password": "Str0ngPassw0rd!",
    "qualification": parsed.get("qualification"),
    "skills": parsed.get("skills", []),
    "experience": parsed.get("experience", []),
    "resume_id": p["resume_id"],
    "channel": "email",
}))
PY
)
REG=$(json_post "$BASE/api/v1/auth/register" "$BODY")
echo "$REG" | python3 -m json.tool
CHALLENGE_ID=$(echo "$REG" | jget "['challenge_id']")
OTP=$(echo "$REG" | jget ".get('dev_otp') or ''")
[ -n "$OTP" ] || { echo "No dev_otp returned. Start the API with DEBUG_RETURN_OTP=true"; exit 1; }

step "3a. Negative: wrong code must be rejected (expect 400)"
WRONG=$([ "$OTP" = "000000" ] && echo 111111 || echo 000000)
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST -H 'Content-Type: application/json' \
  -d "{\"challenge_id\":\"$CHALLENGE_ID\",\"code\":\"$WRONG\"}" "$BASE/api/v1/auth/verify-2fa"

step "3b. Negative: profile without a token must be rejected (expect 401)"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" "$BASE/api/v1/profile"

step "4. Verify 2FA with the correct code"
VERIFY=$(json_post "$BASE/api/v1/auth/verify-2fa" "{\"challenge_id\":\"$CHALLENGE_ID\",\"code\":\"$OTP\"}")
echo "$VERIFY" | python3 -m json.tool
TOKEN=$(echo "$VERIFY" | jget "['access_token']")

step "4b. Negative: the same code cannot be reused (expect 400)"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST -H 'Content-Type: application/json' \
  -d "{\"challenge_id\":\"$CHALLENGE_ID\",\"code\":\"$OTP\"}" "$BASE/api/v1/auth/verify-2fa"

step "5. Load profile preview"
curl -sS -f -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/profile" | python3 -m json.tool

step "6. Edit profile"
curl -sS -f -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"qualification":"B.E. Computer Science and Engineering","skills":["Python","FastAPI","PostgreSQL","Docker"]}' \
  "$BASE/api/v1/profile" | python3 -m json.tool

step "7. Dashboard routing payload"
curl -sS -f -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/dashboard/route" | python3 -m json.tool

printf '\nLifecycle complete.\n'
