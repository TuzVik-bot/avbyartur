import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import CheckConstraint

from app.models import BillingOrder, BillingTariff, ListingPromotion

MIGRATION_0029 = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0029_urgent_promotion_service.py"


def _migration_constraints() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("migration_0029", MIGRATION_0029)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: module._check_sql(tuple(values)) for _table, name, *values in module.TABLES}


def _model_constraints() -> dict[str, str]:
    constraints = {}
    for model in (BillingTariff, BillingOrder, ListingPromotion):
        for constraint in model.__table__.constraints:
            if isinstance(constraint, CheckConstraint) and constraint.name.endswith("_service_code"):
                constraints[constraint.name] = str(constraint.sqltext)
    return constraints


def test_service_code_check_constraints_match_migration_0029():
    assert _model_constraints() == _migration_constraints()


def test_create_all_schema_accepts_urgent_tariff(integration):
    with integration["SessionLocal"]() as db:
        tariff = BillingTariff(
            code=f"urgent-{uuid.uuid4().hex[:8]}",
            service_code="urgent",
            name="Срочная продажа",
            amount=Decimal("5.00"),
            currency="BYN",
            duration_days=7,
            status="disabled",
        )
        db.add(tariff)
        db.commit()
        assert tariff.id is not None
