"""Structural tests for the ToolAuditLog model — no live DB required."""
from backend.models import ToolAuditLog


def test_tool_audit_log_has_expected_columns():
    columns = {c.name for c in ToolAuditLog.__table__.columns}
    assert columns == {"id", "user_id", "tool_name", "arguments", "attested_at"}


def test_tool_audit_log_tablename():
    assert ToolAuditLog.__tablename__ == "tool_audit_logs"


def test_tool_audit_log_user_id_has_fk_to_users():
    user_id_col = ToolAuditLog.__table__.columns["user_id"]
    assert not user_id_col.nullable
    fk_targets = {fk.target_fullname for fk in user_id_col.foreign_keys}
    assert "users.id" in fk_targets
