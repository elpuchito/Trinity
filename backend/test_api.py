"""
TriageForge — API Smoke Tests
Comprehensive programmatic tests for all Phase 1 endpoints.
"""

import requests
import json
import time
import os
import tempfile

BASE = "http://localhost:8000"
PASSED = 0
FAILED = 0
TOTAL = 0


def test(name, fn):
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    try:
        fn()
        PASSED += 1
        print(f"  ✅ {name}")
    except AssertionError as e:
        FAILED += 1
        print(f"  ❌ {name} — {e}")
    except Exception as e:
        FAILED += 1
        print(f"  💥 {name} — EXCEPTION: {e}")


# ============================================
# 1. SYSTEM ENDPOINTS
# ============================================
print("\n🔧 SYSTEM ENDPOINTS")
print("=" * 50)


def test_health():
    r = requests.get(f"{BASE}/health")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["status"] == "healthy", f"Status is {data['status']}"
    assert data["service"] == "TriageForge"
    assert data["version"] == "1.0.0"

test("GET /health returns healthy", test_health)


def test_root():
    r = requests.get(f"{BASE}/")
    assert r.status_code == 200
    data = r.json()
    assert "name" in data
    assert data["docs"] == "/docs"

test("GET / returns API info", test_root)


def test_docs():
    r = requests.get(f"{BASE}/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower() or "openapi" in r.text.lower()

test("GET /docs returns Swagger UI", test_docs)


def test_openapi_schema():
    r = requests.get(f"{BASE}/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "TriageForge"
    assert "/api/incidents" in str(schema["paths"])

test("GET /openapi.json returns valid schema", test_openapi_schema)


# ============================================
# 2. INCIDENT CRUD
# ============================================
print("\n📋 INCIDENT CRUD")
print("=" * 50)

created_ids = []


def test_list_empty_or_existing():
    r = requests.get(f"{BASE}/api/incidents")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list), "Expected a list"

test("GET /api/incidents returns list", test_list_empty_or_existing)


def test_create_incident_text_only():
    r = requests.post(f"{BASE}/api/incidents", data={
        "title": "E2E Test: Payment gateway timeout",
        "description": "Payment processing via Stripe is timing out after 30s. Customers see a blank page after clicking Pay Now. Affects all payment methods.",
        "reporter_name": "Test User",
        "reporter_email": "test@triageforge.dev",
    })
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["title"] == "E2E Test: Payment gateway timeout"
    assert data["status"] == "submitted"
    assert data["severity"] == "UNKNOWN"
    assert data["reporter_email"] == "test@triageforge.dev"
    assert data["id"] is not None
    assert data["triage_report"] is None
    assert data["tickets"] == []
    assert data["notifications"] == []
    created_ids.append(data["id"])

test("POST /api/incidents creates text-only incident", test_create_incident_text_only)


def test_create_incident_with_attachment():
    # Create a fake log file
    log_content = b"""[2026-04-08 15:32:01] ERROR saleor.checkout: PaymentError: Gateway timeout
[2026-04-08 15:32:01] ERROR saleor.checkout: Traceback (most recent call last):
  File "/app/saleor/payment/gateway.py", line 142, in process_payment
    response = gateway.charge(payment_info)
  File "/app/saleor/payment/gateways/stripe/plugin.py", line 89, in charge
    raise PaymentError("Gateway connection timed out after 30000ms")
"""
    files = [("attachments", ("error.log", log_content, "text/plain"))]
    r = requests.post(f"{BASE}/api/incidents", data={
        "title": "E2E Test: Checkout crash with log file",
        "description": "Checkout crashes with PaymentError. See attached log.",
        "reporter_name": "QA Bot",
        "reporter_email": "qa@triageforge.dev",
    }, files=files)
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    data = r.json()
    assert len(data["attachments"]) == 1, f"Expected 1 attachment, got {len(data['attachments'])}"
    att = data["attachments"][0]
    assert att["original_name"] == "error.log"
    assert att["content_type"] == "text/plain"
    assert att["size"] > 0
    created_ids.append(data["id"])

test("POST /api/incidents with file attachment", test_create_incident_with_attachment)


def test_create_incident_with_image():
    # Create a minimal 1x1 pixel PNG
    png_bytes = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
        b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
        b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    files = [("attachments", ("screenshot.png", png_bytes, "image/png"))]
    r = requests.post(f"{BASE}/api/incidents", data={
        "title": "E2E Test: UI broken with screenshot",
        "description": "Product page shows broken layout on mobile. See attached screenshot.",
        "reporter_name": "Mobile Tester",
        "reporter_email": "mobile@triageforge.dev",
    }, files=files)
    assert r.status_code == 201, f"{r.status_code}: {r.text}"
    data = r.json()
    assert len(data["attachments"]) == 1
    assert data["attachments"][0]["content_type"] == "image/png"
    created_ids.append(data["id"])

test("POST /api/incidents with image attachment (multimodal)", test_create_incident_with_image)


def test_create_incident_multiple_attachments():
    files = [
        ("attachments", ("app.log", b"ERROR: NullPointerException", "text/plain")),
        ("attachments", ("trace.json", b'{"trace_id":"abc123"}', "application/json")),
    ]
    r = requests.post(f"{BASE}/api/incidents", data={
        "title": "E2E Test: Multiple attachments",
        "description": "Submitting incident with multiple file types.",
        "reporter_name": "Multi File User",
        "reporter_email": "multi@triageforge.dev",
    }, files=files)
    assert r.status_code == 201
    data = r.json()
    assert len(data["attachments"]) == 2, f"Expected 2, got {len(data['attachments'])}"
    created_ids.append(data["id"])

test("POST /api/incidents with multiple attachments", test_create_incident_multiple_attachments)


def test_get_incident_detail():
    assert len(created_ids) > 0, "No incidents created yet"
    iid = created_ids[0]
    r = requests.get(f"{BASE}/api/incidents/{iid}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == iid
    assert data["title"] == "E2E Test: Payment gateway timeout"
    assert "tickets" in data
    assert "notifications" in data

test("GET /api/incidents/{id} returns full detail", test_get_incident_detail)


def test_get_nonexistent_incident():
    r = requests.get(f"{BASE}/api/incidents/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"

test("GET /api/incidents/{bad_id} returns 404", test_get_nonexistent_incident)


def test_list_incidents_returns_created():
    r = requests.get(f"{BASE}/api/incidents")
    assert r.status_code == 200
    data = r.json()
    titles = [i["title"] for i in data]
    assert any("Payment gateway" in t for t in titles), f"Created incident not found in list: {titles}"

test("GET /api/incidents lists newly created incidents", test_list_incidents_returns_created)


# ============================================
# 3. INCIDENT UPDATES
# ============================================
print("\n🔄 INCIDENT UPDATES")
print("=" * 50)


def test_update_severity():
    iid = created_ids[0]
    r = requests.patch(f"{BASE}/api/incidents/{iid}", json={"severity": "P1"})
    assert r.status_code == 200
    data = r.json()
    assert data["severity"] == "P1", f"Expected P1, got {data['severity']}"

test("PATCH severity to P1", test_update_severity)


def test_update_status():
    iid = created_ids[0]
    r = requests.patch(f"{BASE}/api/incidents/{iid}", json={"status": "triaging"})
    assert r.status_code == 200
    assert r.json()["status"] == "triaging"

test("PATCH status to triaging", test_update_status)


def test_update_assignment():
    iid = created_ids[0]
    r = requests.patch(f"{BASE}/api/incidents/{iid}", json={
        "assigned_team": "Payment Engineering",
        "status": "triaged",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["assigned_team"] == "Payment Engineering"
    assert data["status"] == "triaged"

test("PATCH assign team + triaged status", test_update_assignment)


def test_resolve_incident():
    iid = created_ids[0]
    r = requests.patch(f"{BASE}/api/incidents/{iid}", json={"status": "resolved"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "resolved"
    assert data["resolved_at"] is not None, "resolved_at should be set"

test("PATCH resolve sets resolved_at timestamp", test_resolve_incident)


def test_update_triage_report():
    iid = created_ids[1]
    report = {
        "severity": "P2",
        "affected_service": "checkout",
        "root_cause": "Stripe SDK timeout",
        "confidence": 0.87,
    }
    r = requests.patch(f"{BASE}/api/incidents/{iid}", json={"triage_report": report})
    assert r.status_code == 200
    data = r.json()
    assert data["triage_report"]["severity"] == "P2"
    assert data["triage_report"]["confidence"] == 0.87

test("PATCH triage_report stores JSON correctly", test_update_triage_report)


# ============================================
# 4. FILTERING
# ============================================
print("\n🔍 FILTERING")
print("=" * 50)


def test_filter_by_status():
    r = requests.get(f"{BASE}/api/incidents", params={"status": "resolved"})
    assert r.status_code == 200
    data = r.json()
    for inc in data:
        assert inc["status"] == "resolved", f"Expected resolved, got {inc['status']}"

test("Filter by status=resolved", test_filter_by_status)


def test_filter_by_severity():
    r = requests.get(f"{BASE}/api/incidents", params={"severity": "P1"})
    assert r.status_code == 200
    data = r.json()
    for inc in data:
        assert inc["severity"] == "P1", f"Expected P1, got {inc['severity']}"

test("Filter by severity=P1", test_filter_by_severity)


def test_pagination():
    r = requests.get(f"{BASE}/api/incidents", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    data = r.json()
    assert len(data) <= 2, f"Expected <=2 results, got {len(data)}"

test("Pagination limit=2 works", test_pagination)


# ============================================
# 5. VALIDATION / EDGE CASES
# ============================================
print("\n🛡️ VALIDATION & EDGE CASES")
print("=" * 50)


def test_missing_required_fields():
    r = requests.post(f"{BASE}/api/incidents", data={
        "title": "No description",
        # missing description, reporter_name, reporter_email
    })
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"

test("POST without required fields returns 422", test_missing_required_fields)


def test_invalid_uuid():
    r = requests.get(f"{BASE}/api/incidents/not-a-uuid")
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"

test("GET with invalid UUID returns 422", test_invalid_uuid)


def test_update_nonexistent():
    r = requests.patch(
        f"{BASE}/api/incidents/00000000-0000-0000-0000-000000000000",
        json={"status": "resolved"}
    )
    assert r.status_code == 404

test("PATCH nonexistent incident returns 404", test_update_nonexistent)


# ============================================
# 6. INFRASTRUCTURE CHECKS
# ============================================
print("\n🏗️ INFRASTRUCTURE")
print("=" * 50)


def test_frontend_serves():
    r = requests.get("http://localhost:3000")
    assert r.status_code == 200
    assert "TriageForge" in r.text

test("Frontend serves HTML at :3000", test_frontend_serves)


def test_grafana_serves():
    r = requests.get("http://localhost:3001", allow_redirects=True)
    assert r.status_code == 200

test("Grafana serves at :3001", test_grafana_serves)


def test_chromadb_serves():
    r = requests.get("http://localhost:8500/api/v1/heartbeat")
    assert r.status_code == 200

test("ChromaDB heartbeat at :8500", test_chromadb_serves)


def test_otel_collector():
    # OTel collector exposes metrics on 8888
    r = requests.get("http://localhost:8888/metrics")
    assert r.status_code == 200

test("OTel Collector metrics at :8888", test_otel_collector)


def test_backend_cors():
    r = requests.options(f"{BASE}/api/incidents", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    })
    assert r.status_code == 200
    assert "access-control-allow-origin" in r.headers

test("CORS headers present for frontend origin", test_backend_cors)


# ============================================
# RESULTS
# ============================================
print("\n" + "=" * 50)
print(f"📊 RESULTS: {PASSED}/{TOTAL} passed, {FAILED} failed")
print("=" * 50)

if FAILED > 0:
    print("❌ Some tests failed!")
    exit(1)
else:
    print("🎉 All tests passed!")
    exit(0)
