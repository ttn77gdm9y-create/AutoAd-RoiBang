from pathlib import Path


def test_dev_recover_points_frontend_to_port_8007_and_checks_workflow_catalog():
    script = Path("scripts/dev-recover.sh").read_text(encoding="utf-8")

    assert "VITE_API_BASE_URL=http://127.0.0.1:$BACKEND_PORT/api" in script
    assert "/api/workflow-runs/catalog" in script
