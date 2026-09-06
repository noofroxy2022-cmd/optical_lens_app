"""Phase 1 commercial-schema tests.

Exercised against the real application models / schemas / crud, on a fresh
in-memory SQLite database per test (partial unique indexes, CHECK constraints and
expression indexes are all created by Base.metadata.create_all).
"""
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, schemas, crud, database  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    # Use the exact same enforcement hook the application registers, so these
    # tests exercise the production mechanism rather than a test-only copy.
    event.listen(engine, "connect", database._set_sqlite_pragma)

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ----- builders ---------------------------------------------------------------
def _company(db, name="ACME"):
    c = models.Company(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _catalog(db, company=None, status=models.CatalogStatus.DRAFT):
    if company is None:
        company = _company(db, name=f"CO-{datetime.utcnow().timestamp()}")
    cat = models.Catalog(
        company_id=company.id,
        filename="cat.pdf",
        file_path="/tmp/cat.pdf",
        status=status,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _model(db, company, name="Model A"):
    m = models.LensModel(
        company_id=company.id, name=name, category=models.LensCategory.SINGLE_VISION
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _variant(
    db,
    model,
    material=models.MaterialType.CR39,
    index_value=1.5,
    design_type=models.DesignType.SPHERICAL,
    is_aspherical=False,
    design_variant=None,
    color_variant=None,
    commit=True,
):
    v = models.LensVariant(
        lens_model_id=model.id,
        material=material,
        index_value=index_value,
        design_type=design_type,
        is_aspherical=is_aspherical,
        design_variant=design_variant,
        color_variant=color_variant,
        price=0.0,
    )
    db.add(v)
    if commit:
        db.commit()
        db.refresh(v)
    return v


def _pricing_payload(variant, catalog, **over):
    data = dict(
        variant_id=variant.id,
        availability=schemas.PricingAvailability.STOCK,
        price_pair=100.0,
        currency="EGP",
        source_catalog_id=catalog.id,
    )
    data.update(over)
    return schemas.VariantPricingCreate(**data)


# ----- coating extraction semantics -----------------------------------------
def test_explicit_none_and_not_found_remain_distinct(db):
    company = _company(db)
    catalog = _catalog(db)
    e1 = models.CatalogExtraction(
        catalog_id=catalog.id,
        extracted_name="Lens 1",
        coating_extraction_status=models.CoatingExtractionStatus.EXPLICIT_NONE,
    )
    e2 = models.CatalogExtraction(
        catalog_id=catalog.id,
        extracted_name="Lens 2",
        coating_extraction_status=models.CoatingExtractionStatus.NOT_FOUND,
    )
    db.add_all([e1, e2])
    db.commit()

    assert (
        models.CoatingExtractionStatus.EXPLICIT_NONE
        != models.CoatingExtractionStatus.NOT_FOUND
    )
    rows = {
        r.extracted_name: r.coating_extraction_status
        for r in db.query(models.CatalogExtraction).all()
    }
    assert rows["Lens 1"] is models.CoatingExtractionStatus.EXPLICIT_NONE
    assert rows["Lens 2"] is models.CoatingExtractionStatus.NOT_FOUND
    assert (
        db.query(models.CatalogExtraction)
        .filter(
            models.CatalogExtraction.coating_extraction_status
            == models.CoatingExtractionStatus.NOT_FOUND
        )
        .count()
        == 1
    )


# ----- power range / pricing wiring ----------------------------------------
def test_power_range_without_pricing_id_fails(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    pr = models.PowerRange(
        lens_model_id=model.id,
        variant_id=variant.id,
        sph_min=-2.0,
        sph_max=2.0,
        cyl_min=-2.0,
        cyl_max=0.0,
    )
    db.add(pr)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_rx_variant_pricing_with_zero_power_ranges_succeeds(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    pricing = crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, availability=schemas.PricingAvailability.RX)
    )
    assert pricing.id is not None
    assert pricing.power_ranges == []
    assert pricing.availability is models.PricingAvailability.RX


def test_zero_length_effective_interval_fails(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    now = datetime(2026, 1, 1, 12, 0, 0)
    bad = models.VariantPricing(
        variant_id=variant.id,
        availability=models.PricingAvailability.STOCK,
        price_pair=100.0,
        currency="EGP",
        source_catalog_id=catalog.id,
        effective_from=now,
        effective_to=now,
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ----- current-pricing uniqueness ----------------------------------------
def test_two_stock_prices_with_different_power_scope_coexist(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, power_scope="low", price_pair=100.0)
    )
    crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, power_scope="high", price_pair=150.0)
    )
    current = crud.get_current_pricing_for_variant(db, variant.id)
    assert len(current) == 2
    assert {p.power_scope for p in current} == {"low", "high"}


def test_two_market_scope_values_coexist(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, market_scope="retail", price_pair=100.0)
    )
    crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, market_scope="wholesale", price_pair=90.0)
    )
    current = crud.get_current_pricing_for_variant(db, variant.id)
    assert {p.market_scope for p in current} == {"retail", "wholesale"}


def test_exact_duplicate_current_pricing_blocked(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    crud.create_variant_pricing_internal(db, _pricing_payload(variant, catalog))
    with pytest.raises(IntegrityError):
        crud.create_variant_pricing_internal(db, _pricing_payload(variant, catalog))
    db.rollback()


def test_no_both_pricing(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    # enum has no BOTH
    assert not hasattr(models.PricingAvailability, "BOTH")
    # and the DB CHECK rejects it even on a raw insert
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO variant_pricing "
                "(variant_id, availability, price_pair, currency, source_catalog_id, effective_from) "
                "VALUES (:v, 'BOTH', 100.0, 'EGP', :c, :t)"
            ),
            {"v": variant.id, "c": catalog.id, "t": datetime.utcnow()},
        )
        db.commit()
    db.rollback()


def test_history_is_append_only(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)

    p1 = crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, price_pair=100.0)
    )
    p1_id = p1.id
    at = p1.effective_from + timedelta(days=30)
    p2 = crud.supersede_pricing(
        db, p1_id, _pricing_payload(variant, catalog, price_pair=200.0), at=at
    )

    # no public manual mutation surface
    assert not hasattr(crud, "update_variant_pricing")
    assert not hasattr(crud, "delete_variant_pricing")

    history = crud.get_pricing_history(db, variant.id)
    assert [h.price_pair for h in history] == [100.0, 200.0]

    p1_reloaded = db.get(models.VariantPricing, p1_id)
    assert p1_reloaded.price_pair == 100.0  # original untouched
    assert p1_reloaded.effective_to == at
    assert p2.effective_from == at
    assert p2.effective_to is None
    assert len(crud.get_current_pricing_for_variant(db, variant.id)) == 1


def test_price_pair_preserved_exactly(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, price_pair=1234.5)
    )
    db.expire_all()
    reloaded = crud.get_current_pricing_for_variant(db, variant.id)[0]
    assert reloaded.price_pair == 1234.5


@pytest.mark.parametrize(
    "value",
    [Decimal("0.01"), Decimal("19.99"), Decimal("1234.56"),
     Decimal("2500.00"), Decimal("99999999.99")],
)
def test_price_pair_decimal_exact_round_trip(db, value):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    created = crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, price_pair=value)
    )
    # exact on the freshly-created object
    assert isinstance(created.price_pair, Decimal)
    assert created.price_pair == value

    # exact after a real reload from the DB
    db.expire_all()
    reloaded = db.get(models.VariantPricing, created.id)
    assert isinstance(reloaded.price_pair, Decimal)
    assert reloaded.price_pair == value
    # scale preserved to the cent, no binary drift
    assert reloaded.price_pair.quantize(Decimal("0.01")) == value.quantize(Decimal("0.01"))
    assert str(reloaded.price_pair) == str(value.quantize(Decimal("0.01")))


def test_pricing_response_schema_is_decimal(db):
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    row = crud.create_variant_pricing_internal(
        db, _pricing_payload(variant, catalog, price_pair=Decimal("42.00"))
    )
    resp = schemas.VariantPricingResponse.model_validate(row)
    assert isinstance(resp.price_pair, Decimal)
    assert resp.price_pair == Decimal("42.00")


# ----- NULL optical-identity hole prevention --------------------------------
def _raw_insert_variant(db, model_id, **cols):
    """Raw INSERT bypassing the ORM. All NOT NULL columns except the ones under
    test are supplied, so a failure isolates to the column being probed."""
    keys = ", ".join(cols)
    params = ", ".join(f":{k}" for k in cols)
    db.execute(
        text(
            f"INSERT INTO lens_variants "
            f"(lens_model_id, material, index_value, availability, price, is_active, {keys}) "
            f"VALUES (:mid, 'CR39', 1.5, 'STOCK', 0.0, 1, {params})"
        ),
        {"mid": model_id, **cols},
    )
    db.commit()


def test_null_design_type_rejected(db):
    company = _company(db)
    model = _model(db, company)
    with pytest.raises(IntegrityError):
        _raw_insert_variant(db, model.id, design_type=None, is_aspherical=0)
    db.rollback()


def test_null_is_aspherical_rejected(db):
    company = _company(db)
    model = _model(db, company)
    with pytest.raises(IntegrityError):
        _raw_insert_variant(db, model.id, design_type="SPHERICAL", is_aspherical=None)
    db.rollback()


def test_null_optical_identity_cannot_bypass_uq_variant_identity(db):
    """Two variants identical except NULL optical-identity fields must not both persist."""
    company = _company(db)
    model = _model(db, company)
    # a legitimate row (defaults: SPHERICAL / not aspherical / no commercial axes)
    _variant(db, model)
    # trying to smuggle a duplicate past the unique index via NULL optical fields
    # fails at NOT NULL, before uniqueness even matters
    with pytest.raises(IntegrityError):
        _raw_insert_variant(db, model.id, design_type=None, is_aspherical=None)
    db.rollback()
    # and an explicit same-identity duplicate still collides on uq_variant_identity
    with pytest.raises(IntegrityError):
        _raw_insert_variant(db, model.id, design_type="SPHERICAL", is_aspherical=0)
    db.rollback()
    assert db.query(models.LensVariant).count() == 1


# ----- coating human-review update schema ---------------------------------
def _extraction(db, catalog, status=models.CoatingExtractionStatus.NOT_FOUND):
    ext = crud.create_extraction(
        db,
        schemas.CatalogExtractionCreate(
            catalog_id=catalog.id,
            extracted_name="Some Lens",
            coating_extraction_status=schemas.CoatingExtractionStatus(status.value),
        ),
    )
    return ext


def test_coating_review_update_not_found_to_resolved(db):
    catalog = _catalog(db)
    coating = crud.get_or_create_coating(db, code="HMC", name="Hard Multi Coat")
    ext = _extraction(db, catalog)
    assert ext.coating_extraction_status is models.CoatingExtractionStatus.NOT_FOUND

    updated = crud.update_extraction(
        db,
        ext.id,
        schemas.CatalogExtractionUpdate(
            coating_extraction_status=schemas.CoatingExtractionStatus.RESOLVED,
            coating_id=coating.id,
            extracted_coating="HMC",
            coating_confidence=0.95,
            coating_review_notes="confirmed by reviewer",
        ),
    )
    db.expire_all()
    reloaded = db.get(models.CatalogExtraction, ext.id)
    assert reloaded.coating_extraction_status is models.CoatingExtractionStatus.RESOLVED
    assert reloaded.coating_id == coating.id
    assert reloaded.extracted_coating == "HMC"
    assert reloaded.coating_confidence == 0.95
    assert reloaded.coating_review_notes == "confirmed by reviewer"


def test_coating_review_update_not_found_to_explicit_none(db):
    catalog = _catalog(db)
    ext = _extraction(db, catalog)
    crud.update_extraction(
        db,
        ext.id,
        schemas.CatalogExtractionUpdate(
            coating_extraction_status=schemas.CoatingExtractionStatus.EXPLICIT_NONE,
            coating_review_notes="catalogue explicitly lists no coating",
        ),
    )
    db.expire_all()
    reloaded = db.get(models.CatalogExtraction, ext.id)
    assert reloaded.coating_extraction_status is models.CoatingExtractionStatus.EXPLICIT_NONE
    assert reloaded.coating_id is None


# ----- SQLite foreign-key enforcement (real engine config) ----------------
def test_configured_engine_enforces_sqlite_foreign_keys():
    """The application's own engine must report PRAGMA foreign_keys = 1 on connect."""
    if database.engine.dialect.name != "sqlite":
        pytest.skip("configured engine is not SQLite")
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_fixture_engine_enforces_sqlite_foreign_keys(db):
    """The hook is the shared application hook, so the test engine enforces it too."""
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


# ----- historical-pricing deletion safety --------------------------------
def test_deleting_variant_with_pricing_is_rejected_and_pricing_survives(db):
    """A: hard-deleting a LensVariant that has VariantPricing must fail; pricing survives."""
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    pricing = crud.create_variant_pricing_internal(db, _pricing_payload(variant, catalog))
    pricing_id = pricing.id
    variant_id = variant.id

    with pytest.raises(IntegrityError):
        crud.delete_lens_variant(db, variant_id)
    db.rollback()

    assert db.get(models.VariantPricing, pricing_id) is not None
    assert db.get(models.LensVariant, variant_id) is not None


def test_deleting_model_with_priced_variant_is_rejected_and_pricing_survives(db):
    """B: hard-deleting a LensModel whose variant has VariantPricing must fail; pricing survives."""
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    pricing = crud.create_variant_pricing_internal(db, _pricing_payload(variant, catalog))
    pricing_id, model_id, variant_id = pricing.id, model.id, variant.id

    with pytest.raises(IntegrityError):
        crud.delete_lens_model(db, model_id)
    db.rollback()

    assert db.get(models.VariantPricing, pricing_id) is not None
    assert db.get(models.LensVariant, variant_id) is not None
    assert db.get(models.LensModel, model_id) is not None


def test_deleting_pricing_with_power_ranges_is_rejected_and_both_survive(db):
    """C: direct hard-delete of a VariantPricing that has PowerRanges must fail; both survive."""
    company = _company(db)
    model = _model(db, company)
    variant = _variant(db, model)
    catalog = _catalog(db)
    pricing = crud.create_variant_pricing_internal(db, _pricing_payload(variant, catalog))
    pr = models.PowerRange(
        lens_model_id=model.id,
        variant_id=variant.id,
        pricing_id=pricing.id,
        sph_min=-2.0,
        sph_max=2.0,
        cyl_min=-2.0,
        cyl_max=0.0,
    )
    db.add(pr)
    db.commit()
    pricing_id, pr_id = pricing.id, pr.id

    with pytest.raises(IntegrityError):
        db.delete(pricing)
        db.commit()
    db.rollback()

    assert db.get(models.VariantPricing, pricing_id) is not None
    assert db.get(models.PowerRange, pr_id) is not None


# ----- variant identity ------------------------------------------------------
def test_two_design_variant_values_coexist(db):
    company = _company(db)
    model = _model(db, company)
    _variant(db, model, design_variant="Free Form")
    _variant(db, model, design_variant="High Definition")
    assert db.query(models.LensVariant).count() == 2


def test_different_optical_geometry_variants_do_not_collapse(db):
    company = _company(db)
    model = _model(db, company)
    _variant(
        db, model, design_type=models.DesignType.SPHERICAL, is_aspherical=False,
        design_variant="Core",
    )
    _variant(
        db, model, design_type=models.DesignType.ASPHERICAL, is_aspherical=True,
        design_variant="Core",
    )
    assert db.query(models.LensVariant).count() == 2


def test_stored_display_casing_preserved(db):
    company = _company(db)
    model = _model(db, company)
    _variant(
        db, model, design_variant="Free Form", color_variant="Transmatic/G/B"
    )
    db.expire_all()
    v = db.query(models.LensVariant).one()
    assert v.design_variant == "Free Form"
    assert v.color_variant == "Transmatic/G/B"


def test_case_only_identity_duplicate_blocked(db):
    company = _company(db)
    model = _model(db, company)
    _variant(db, model, design_variant="Free Form")
    with pytest.raises(IntegrityError):
        _variant(db, model, design_variant="free form")
    db.rollback()


# ----- catalog lifecycle ---------------------------------------------------
def test_one_confirmed_catalog_per_company(db):
    company = _company(db)
    # multiple drafts are fine
    _catalog(db, company, status=models.CatalogStatus.DRAFT)
    _catalog(db, company, status=models.CatalogStatus.DRAFT)
    _catalog(db, company, status=models.CatalogStatus.CONFIRMED)
    with pytest.raises(IntegrityError):
        _catalog(db, company, status=models.CatalogStatus.CONFIRMED)
    db.rollback()

    # a different company can still have its own confirmed catalog
    other = _company(db, name="OTHER")
    _catalog(db, other, status=models.CatalogStatus.CONFIRMED)
    assert (
        db.query(models.Catalog)
        .filter(models.Catalog.status == models.CatalogStatus.CONFIRMED)
        .count()
        == 2
    )
