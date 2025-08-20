.PHONY: setup run dev docker-build docker-run index-materials test k8s-stage k8s-prod docker-buildx

setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run:
	. .venv/bin/activate && FLASK_APP=app.main:app flask run --host 0.0.0.0 --port 8000

dev:
	. .venv/bin/activate && gunicorn -b 0.0.0.0:8000 app.main:app --reload

docker-build:
	docker build -t msa-ai:latest .

docker-buildx:
	docker buildx build --platform linux/amd64,linux/arm64 -t YOUR_REGISTRY/msa-ai:latest --push .

docker-run:
	docker run --env-file .env -p 8000:8000 --name msa-ai --rm msa-ai:latest

index-materials:
	. .venv/bin/activate && python scripts/index_materials.py data/materials.json

test:
	. .venv/bin/activate && pytest -q --disable-warnings --maxfail=1

k8s-stage:
	kubectl apply -f k8s/ai-deployment.yaml

k8s-prod:
	kubectl apply -f k8s/prod/ai-deployment.yaml

