## 1. 기능
- **학습 조언 생성**: 시험 결과를 바탕으로 초등학생 친화적인 한국어 반말 톤으로 개인화 조언 생성. 학생 이름(아/야) 포함, 칭찬 표현 다양화, 오답별 간단 해설+개선 방법 반영, 단계별 명확한 안내.
- **문항 피드백**: 단문 답안에 대해 RAG 근거를 포함한 피드백 생성(최소 1개 evidence 시도).
- **RAG 검색**: MongoDB Atlas Vector Search 기반 상위 k 문서 스니펫/점수 반환. 과목/학년 필터 필수 반영(영문/국문/별칭 모두 매칭).
- **자동 채점(샘플)**: 객관식(정답 일치), 단답(정규화+허용정답 집합).
- **DB 연동**: 시험/문항/제출/답안을 읽어 종합 컨텍스트 구성 후 조언 생성. 최초 호출 시에만 `submissions.feedback`에 저장.
- **관찰성/운영**: Prometheus 메트릭(`/metrics`), Health/Ready(`/healthz`, `/readyz`), 요청 상관관계 ID(`X-Correlation-ID`).

## 2. 기술 스택
- **Backend**: Flask (Gunicorn 배포 권장)
- **LLM**: Azure OpenAI (Chat, Embeddings)
- **RAG**: MongoDB Atlas (Vector Search: knnVector/knnBeta), Azure Embeddings(1536차원)
- **DB**: PostgreSQL (SQLAlchemy/psycopg2)
- **Validation/Schema**: Pydantic v2
- **Observability**: prometheus_client
- **Others**: requests/bs4/pdfminer/pymupdf(자료 구축 스크립트)

## 3. 데이터베이스 스키마
서비스가 참조/저장하는 핵심 테이블(컬럼은 서비스에서 사용하는 최소 컬럼만 기재)

- `classes`
  - `id` (PK)
  - `name` (TEXT)
  - `subject` (INT) 0: 과학, 1: 수학, 2: 영어, 3: 국어
  - `grade` (TEXT) 예: '3', '4'
- `exams`
  - `id` (PK)
  - `class_id` (FK → classes.id)
- `questions`
  - `id` (PK)
  - `exam_id` (FK → exams.id)
  - `qtype` (TEXT) 'MCQ' | 'SHORT'
  - `body` (TEXT) 문제 본문
  - `choices` (JSONB) 객관식 선지(선택)
  - `answer_key` (JSONB|TEXT) 정답 또는 허용 정답 배열
  - (레거시 호환) `type`(MC|SA), `stem`, `options`
- `submissions`
  - `id` (PK)
  - `exam_id` (FK → exams.id)
  - `user_id` (FK → users)
  - `submitted_at` (TIMESTAMPTZ)
  - `total_score` (INT)
  - `feedback` (TEXT) 조언 저장 컬럼(최초 NULL일 때만 작성)
  - (레거시 호환) `submission_id`, `test_id`, `student_id`, `answers`, `score`, `status`, `created_at`
- `submission_answers`
  - `exam_id` (PK part)
  - `user_id` (PK part)
  - `question_id` (PK part)
  - `answer_text` (TEXT)
  - `is_correct` (BOOLEAN)
  - `score` (INT)
  - `elapsed_time_seconds` (INT)
- `users`
  - `user_id` (PK)
  - `email`, `name`

컨텍스트 구성 시 각 문항 아이템 형태:
```json
{
  "stem": "문제 본문",
  "qtype": "MCQ|SHORT",
  "choices": ["..."],
  "answer": "정답" | ["허용정답"],
  "studentAnswer": "학생답",
  "correct": true|false|null,
  "timeSpent": 25
}
```

## 4. 설정
### 4-a. 환경 변수 설정 (`.env`)
```env
# Azure OpenAI
SE_KEYVAULT=false
AZURE_OPENAI_API_KEY=YOUR_KEY
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-small
OPENAI_TEMPERATURE=0.1

# MongoDB Atlas (RAG)
MONGODB_URI=mongodb+srv://USER:PASS@cluster/app?retryWrites=true&w=majority
MONGODB_DB=edu_platform
MONGODB_COLLECTION_MATERIALS=materials
MONGODB_SEARCH_INDEX=materials_vector_index

# PostgreSQL
POSTGRESQL_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/ai_service

# App
FLASK_ENV=production
LOG_LEVEL=INFO
```

### 4-b. 데이터베이스 설정
- 로컬 PostgreSQL(docker 예시, 포트 5433 사용 권장) 기동 후 `.env`의 URL과 일치시켜 주세요.
- 서비스 기동 시 안전한 컬럼 보강(ALTER)과 `submission_answers` 테이블 생성을 시도합니다.
- 초기 데이터(예제) 삽입은 제공 SQL/스크립트를 참고하세요.

임베딩 인덱스(Atlas Search):
```json
{ "mappings": { "dynamic": false, "fields": { "vector": { "type": "knnVector", "dimensions": 1536, "similarity": "cosine" } } } }
```

## 5. API 사용법
모든 응답은 UTF-8 한국어. 조언/피드백은 초등학생에게 다정한 반말 톤, 학생 이름에 '아/야' 적용.

- 학습 조언(시험 단위, DB→RAG→조언 저장)
  - POST `/api/exams/{examId}/ai/advice`
  - Body: `{ "studentId": "10" }`
  - 동작: DB에서 시험/문항/답안/점수/과목/학년/학생명을 읽고, 오답 중심 RAG 쿼리+컨텍스트로 조언 생성 → `submissions.feedback`이 NULL일 때만 저장
  - 응답: `{ "status":"OK", "stored": true|false }`

- 문항 피드백(증거 포함 시도)
  - POST `/api/exams/{examId}/answers/{answerId}/ai/feedback`
  - Body 예: `{ "studentId":"10", "submissionId":"sub-1", "answer":"분수는...", "materialIds":["mat-001"] }`
  - 응답: `{ "status":"OK", "feedback":"...", "evidence":[{ material_id, title, snippet, score }] }`

- RAG 검색
  - GET `/api/ai/rag?query=...&topK=5[&subject=&grade=&materialIds=a,b]`
  - subject는 `math|english|korean|science` 또는 `수학|영어|국어|과학` 모두 허용, grade는 3/4 문자열/숫자 모두 허용
  - 응답: `[ { docId, title, snippets:["..."] } ]`

- 내부(개발) API
  - POST `/api/v1/evaluate` / `/api/v1/evaluate/batch`
  - POST `/api/v1/search`
  - POST `/api/v1/grade`

헬스/메트릭:
- GET `/healthz`, `/readyz`, `/metrics`

## 6. 테스트 환경
### 로컬 실행(venv)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install --no-cache-dir -r requirements.txt
make run   # 또는 make dev
curl -s http://localhost:8000/healthz
```

### Docker 배포
```bash
# 이미지 빌드
make docker-build
# 실행 (로컬 .env 사용)
make docker-run
```

### Buildx + 레지스트리 푸시
```bash
# YOUR_REGISTRY를 실제 레지스트리로 변경 (ex: ghcr.io/org, youracr.azurecr.io)
make docker-buildx
```

### Kubernetes 배포
```bash
# 네임스페이스 선택 시 -n 추가
# .env에서 Secret 생성 후 배포
make k8s-stage   # 스테이지(리소스 요청/프로브 포함)
make k8s-prod    # 프로덕션(2 replicas, 강화된 리소스)
```
- 매니페스트: `k8s/ai-deployment.yaml`, `k8s/prod/ai-deployment.yaml`
  - readiness: `/readyz`, liveness: `/healthz`
  - imagePullPolicy: IfNotPresent, 기본 리소스 요청/제한 포함
  - Secret: `ai-env` (자동 생성: `.env` 기반)

### Azure(AKS/Container Apps) 참고
- 레지스트리: `az acr build` 또는 로컬 buildx 후 `az acr login && docker push`
- AKS: 위 K8s 매니페스트 사용. `image: <youracr>.azurecr.io/msa-ai:latest`
- Azure OpenAI/Key Vault: `.env` 또는 K8s Secret로 주입(SE_KEYVAULT=true 사용 시 Key Vault에서 키 조회 로직 지원)

## 7. 에러 처리
- 입력 검증 오류(Pydantic): HTTP 400 `{"error":"validation_error", ...}`
- LLM 호출 실패/재시도 초과: HTTP 202 `{"status":"PENDING"}`
- 서버 내부 오류: HTTP 500 (JSON 또는 표준 Flask 에러)
- 공통 헤더: 요청/응답에 `X-Correlation-ID` 포함

운영 팁
- `.env`는 절대 커밋하지 마세요(Secrets/ConfigMap로 주입).
- Atlas 인덱스/차원/경로(`vector`)가 코드와 일치하는지 확인.
- DB의 `classes.subject`(0~3), `classes.grade`('3'/'4')는 RAG 필터에 직접 반영됩니다.
- RAG 유사도가 낮아도 풍부한 문항 컨텍스트로 LLM이 답변을 생성하도록 프롬프트에 컨텍스트/증거를 동시 전달합니다.
