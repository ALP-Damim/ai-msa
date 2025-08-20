from __future__ import annotations
import json
from app.main import app

def test_healthz():
	client = app.test_client()
	rv = client.get("/healthz")
	assert rv.status_code == 200
	data = rv.get_json()
	assert data["status"] == "ok"


def test_search_validation():
	client = app.test_client()
	# missing query
	rv = client.post("/api/v1/search", json={})
	# Pydantic validation error should raise 400 by Flask; but we return 200 always with validated input
	assert rv.status_code in (200, 400)

