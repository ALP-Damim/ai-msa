### MSA AI Microservice (Flask + RAG + Azure OpenAI)

초등학생 대상: 항상 한국어로, 다정한 톤으로 평가/조언을 생성합니다. Atlas Vector Search, Azure OpenAI를 사용하며 조언/피드백/RAG 검색/채점을 제공합니다.

#### 요구사항
- Python 3.11
- MongoDB Atlas (Search Index: vector=knnVector 1536 cosine)
- Azure OpenAI (Endpoint/Key or Key Vault)
- Docker/Kubernetes(선택)

#### 설치(venv)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install --no-cache-dir -r requirements.txt
```

#### 환경변수(.env 예시) — 비공개 유지
```
SE_KEYVAULT=false
AZURE_OPENAI_API_KEY=***
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-small
OPENAI_TEMPERATURE=0.1

MONGODB_URI=***
MONGODB_DB=edu_platform
MONGODB_COLLECTION_MATERIALS=materials
MONGODB_SEARCH_INDEX=materials_vector_index

POSTGRESQL_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/ai_service
FLASK_ENV=production
LOG_LEVEL=INFO
EMBED_MAX_CHARS=3500
```
- .env, PDF 등 민감/대용량 파일은 이미 `.gitignore` 처리됨

#### Atlas Search 인덱스(JSON)
```json
{ "mappings": { "dynamic": false, "fields": { "vector": { "type": "knnVector", "dimensions": 1536, "similarity": "cosine" } } } }
```

#### 자료 임베딩
```bash
# 예: 국어/영어/수학/과학 JSON 디렉토리 단위
python scripts/index_materials.py materials/korean
python scripts/index_materials.py materials/english
python scripts/index_materials.py materials/math
python scripts/index_materials.py materials/science
```

#### 서버 실행
```bash
make dev
# health
curl -s http://localhost:8000/healthz
```

#### API 요약
- POST `/api/v1/evaluate` / `/api/v1/evaluate/batch` (문항별 평가+조언, 한국어, evidence 포함 시도)
- POST `/api/exams/{examId}/ai/advice` (결과 페이지 조언, `[ {title, body} ]`)
- POST `/api/exams/{examId}/answers/{answerId}/ai/feedback`
- GET `/api/ai/rag?query=...&topK=5[&subject=&grade=&materialIds=a,b]`
- POST `/api/v1/search`(JSON)도 존재
- Prometheus: `/metrics`, 헬스/레디: `/healthz`, `/readyz`

#### 보안/운영
- Key/URI는 절대 커밋 금지(.env 로컬/Secret로 주입)
- 요청 헤더 `X-Correlation-ID` 지원(분산 추적)
- 응답은 UTF-8(한글 이스케이프 없음)

#### Docker/K8s(선택)
```bash
make docker-build        # 단일 아키텍처
make docker-buildx       # multi-arch + push (YOUR_REGISTRY 설정 필요)
# K8s
kubectl create secret generic ai-env --from-env-file=.env -n your-ns
kubectl apply -f k8s/ai-deployment.yaml -n your-ns
```

#### 테스트
```bash
pytest -q --disable-warnings --maxfail=1
```

---
### GitHub 업로드 가이드
1) 원격 추가
```bash
git init  # (처음이라면)
git remote add origin https://github.com/ALP-Damim/ai-msa.git
```
2) 민감정보 확인(비워두기)
- `.env` 없음 확인
- `pdf/` 등 대용량 제외 확인
3) 커밋/푸시
```bash
git add .
git commit -m "feat: AI microservice (Flask+RAG), templates, metrics, tests"
git branch -M main
git push -u origin main
```

필요 시 GitHub Actions로 CI(테스트/빌드) 추가해 드릴 수 있습니다.
