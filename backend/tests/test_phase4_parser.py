"""Phase 4 - commercial parser enrichment.

Drives the parser's structure-level helpers with synthetic table/context data
(no real PDF) and verifies persistence into CatalogExtraction.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base  # noqa: E402
from app import models, database  # noqa: E402
from app.pdf_hybrid_parser import (  # noqa: E402
    PDFHybridParser, ParserContext, ExtractedPowerRange, ExtractedLensModel,
)


@pytest.fixture()
def parser():
    return PDFHybridParser(use_vision=False)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", database._set_sqlite_pragma)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _ctx(**kw):
    return ParserContext(**kw)


def _rows(parser, table, ctx=None):
    return parser._parse_table(table, ctx or _ctx(availability="stock"))


# ===========================================================================
# A. Free Form -> design_variant, NOT design_type
# ===========================================================================
def test_A_free_form_is_design_variant_not_design_type(parser):
    tbl = [["SPH", "CYL", "Price", "Design"],
           ["-6.00 to 0.00", "-2.00", "100", "Free Form"]]
    r = _rows(parser, tbl)[0]
    assert r.design_variant == "Free Form"
    assert r.design_type == "spherical"          # geometry untouched
    assert r.design_type != "free_form"


# ===========================================================================
# B. Core / Advance / Premium stay distinct
# ===========================================================================
def test_B_core_advance_premium_distinct(parser):
    tbl = [["SPH", "CYL", "Price", "Design"]]
    for d in ("Core", "Advance", "Premium"):
        tbl.append(["-6.00 to 0.00", "-2.00", "100", d])
    got = {r.design_variant for r in _rows(parser, tbl)}
    assert got == {"Core", "Advance", "Premium"}


# ===========================================================================
# C. D Type / KT Type stay distinct
# ===========================================================================
def test_C_d_type_kt_type_distinct(parser):
    tbl = [["SPH", "CYL", "Price", "Design"],
           ["-6.00 to 0.00", "-2.00", "100", "D Type"],
           ["-6.00 to 0.00", "-2.00", "120", "KT Type"]]
    got = {r.design_variant for r in _rows(parser, tbl)}
    assert got == {"D Type", "KT Type"}


# ===========================================================================
# D. Clear vs Transmatic / Polz / DWEAR captured as color_variant
# ===========================================================================
def test_D_color_variants_captured(parser):
    tbl = [["SPH", "CYL", "Price", "Color"]]
    for c in ("Clear", "Transmatic/G/B", "Polz/G/B", "DWEAR"):
        tbl.append(["-6.00 to 0.00", "-2.00", "100", c])
    got = [r.color_variant for r in _rows(parser, tbl)]
    assert got == ["Clear", "Transmatic/G/B", "Polz/G/B", "DWEAR"]


# ===========================================================================
# E. numeric "300" cannot become color_variant
# ===========================================================================
def test_E_numeric_is_never_color_variant(parser):
    tbl = [["SPH", "CYL", "Price", "Color"],
           ["-6.00 to 0.00", "-2.00", "100", "300"]]
    r = _rows(parser, tbl)[0]
    assert r.color_variant is None
    assert r.price == 100.0


# ===========================================================================
# F. add-on treatment rows -> zero base lens extraction rows
# ===========================================================================
def test_F_addon_rows_produce_no_base_rows(parser):
    tbl = [["Item", "SPH", "CYL", "Price"],
           ["Clear", "-6.00 to 0.00", "-2.00", "100"],
           ["Blue Cut", "", "", "50"],
           ["Mirror", "", "", "80"],
           ["Hi Power", "", "", "40"]]
    rows = _rows(parser, tbl)
    assert len(rows) == 1
    assert rows[0].price == 100.0


# ===========================================================================
# G. Egypt vs Out Of Egypt -> different market_scope
# ===========================================================================
def test_G_market_scope_from_context(parser):
    tbl = [["SPH", "CYL", "Price"], ["-6.00 to 0.00", "-2.00", "100"]]
    c_eg = _ctx(availability="stock")
    parser._update_context_from_text(c_eg, "Finished Single Vision - Egypt")
    c_out = _ctx(availability="stock")
    parser._update_context_from_text(c_out, "Finished Single Vision - Out Of Egypt")
    assert _rows(parser, tbl, c_eg)[0].market_scope == "Egypt"
    assert _rows(parser, tbl, c_out)[0].market_scope == "Out Of Egypt"


# ===========================================================================
# H. Finished Single Vision Out Of Egypt resolves STOCK from context
# ===========================================================================
def test_H_finished_sv_context_resolves_stock(parser):
    ctx = _ctx()
    parser._update_context_from_text(ctx, "Finished Single Vision  -  Out Of Egypt")
    assert ctx.availability == "stock" and ctx.availability_explicit is True
    tbl = [["SPH", "CYL", "Price"], ["-6.00 to 0.00", "-2.00", "100"]]
    r = _rows(parser, tbl, ctx)[0]
    assert r.availability == "stock"
    assert r.market_scope == "Out Of Egypt"


# ===========================================================================
# I. RX without range is valid and NOT flagged for missing PowerRange
# ===========================================================================
def test_I_rx_without_range_not_flagged_for_range(parser):
    tbl = [["Price", "Coating"], ["400", "-"]]
    ctx = _ctx(availability="rx", availability_explicit=True)
    rows = _rows(parser, tbl, ctx)
    assert len(rows) == 1
    r = rows[0]
    assert r.availability == "rx"
    assert r.has_range is False
    assert "STOCK without PowerRange" not in r.review_reasons
    assert r.review_status == "pending"          # coating explicit_none -> resolved


# ===========================================================================
# J. STOCK without range is review / blocking
# ===========================================================================
def test_J_stock_without_range_is_blocking(parser):
    tbl = [["Price", "Coating"], ["400", "-"]]
    ctx = _ctx(availability="stock", availability_explicit=True)
    r = _rows(parser, tbl, ctx)[0]
    assert r.availability == "stock"
    assert r.review_status == "needs_review"
    assert "STOCK without PowerRange" in r.review_reasons


# ===========================================================================
# K. two STOCK prices with different PowerRanges stay separate
# ===========================================================================
def test_K_two_stock_prices_two_ranges_not_merged(parser):
    tbl = [["SPH", "CYL", "Price", "Design", "Color"],
           ["-6.00 to 0.00", "-2.00", "2500", "Core", "Clear"],
           ["0.00 to +4.00", "-2.00", "5500", "Core", "Clear"]]
    rows = _rows(parser, tbl)
    assert len(rows) == 2
    assert {(r.sph_min, r.sph_max, r.price) for r in rows} == {
        (-6.0, 0.0, 2500.0), (0.0, 4.0, 5500.0)
    }


# ===========================================================================
# L. plus / minus groups are not merged
# ===========================================================================
def test_L_plus_minus_groups_not_merged(parser):
    tbl = [["Group", "SPH", "CYL", "Price"],
           ["Plus", "+0.25 to +6.00", "-2.00", "300"],
           ["Minus", "-0.25 to -8.00", "-2.00", "350"]]
    rows = _rows(parser, tbl)
    assert len(rows) == 2
    prices = sorted(r.price for r in rows)
    assert prices == [300.0, 350.0]
    assert rows[0].sph_max != rows[1].sph_max


# ===========================================================================
# M. coating explicit_none distinct from not_found
# ===========================================================================
def test_M_explicit_none_vs_not_found(parser):
    with_col = [["SPH", "CYL", "Price", "Coating"], ["-6.00 to 0.00", "-2.00", "100", "-"]]
    without_col = [["SPH", "CYL", "Price"], ["-6.00 to 0.00", "-2.00", "100"]]
    a = _rows(parser, with_col)[0]
    b = _rows(parser, without_col)[0]
    assert a.coating_status == "explicit_none"
    assert b.coating_status == "not_found"
    assert a.coating_status != b.coating_status


# ===========================================================================
# N. family resolves only from relationship evidence, uniquely
# ===========================================================================
def test_N_unique_relation_resolves_family(parser):
    ctx = _ctx(availability="rx", category="progressive", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Opal", "availability": "stock", "category": "single_vision",
         "market": "Egypt", "terms": {"emi"}},
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Outside Egypt", "terms": {"astro", "core"}},
    ]
    assert parser._resolve_family(ctx, {"astro"}) == "Aquila"
    assert parser._assign_family(ctx, [ExtractedPowerRange(sph_min=0.0, sph_max=0.0,
                                                          coating="Astro", price=1.0)]) == "Aquila"


# ===========================================================================
# O. two compatible families -> needs_review, model left unresolved
# ===========================================================================
def test_O_two_compatible_families_needs_review(parser):
    ctx = _ctx(availability="rx", category="progressive", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
        {"family": "Falcon", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
    ]
    rows = [ExtractedPowerRange(sph_min=-6.0, sph_max=0.0, has_range=True, price=100.0)]
    name = parser._assign_family(ctx, rows)
    assert name == parser.UNRESOLVED_FAMILY
    assert rows[0].review_status == "needs_review"
    assert "ambiguous/unresolved product family" in rows[0].review_reasons


def test_O_zero_compatible_families_needs_review(parser):
    ctx = _ctx(availability="rx", category="bifocal", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
    ]
    rows = [ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=100.0)]
    assert parser._assign_family(ctx, rows) == parser.UNRESOLVED_FAMILY
    assert "ambiguous/unresolved product family" in rows[0].review_reasons


def test_family_never_resolves_from_price_or_heading(parser):
    ctx = _ctx(availability="stock", category="single_vision", market="Egypt")
    ctx.relations = []                       # no relationship evidence at all
    rows = [ExtractedPowerRange(sph_min=-6.0, sph_max=0.0, has_range=True, price=999.0)]
    name = parser._assign_family(ctx, rows)
    assert name == parser.UNRESOLVED_FAMILY  # price / section heading never used
    assert "ambiguous/unresolved product family" in rows[0].review_reasons


def test_market_key_normalises_out_of_vs_outside(parser):
    assert parser._market_key("Out Of Egypt") == parser._market_key("Outside Egypt")
    assert parser._market_key("Egypt") != parser._market_key("Out Of Egypt")


# ===========================================================================
# P. extracted commercial fields survive save_extractions_to_db
# ===========================================================================
def test_P_commercial_fields_persist(parser, db):
    company = models.Company(name="ACME"); db.add(company); db.commit(); db.refresh(company)
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)

    pr = ExtractedPowerRange(
        sph_min=-6.0, sph_max=0.0, cyl_min=-2.0, cyl_max=0.0, has_range=True,
        index_value=1.5, material="CR39", availability="stock", price=1234.56,
        design_variant="Free Form", color_variant="Transmatic/G/B",
        market_scope="Egypt", coating="HMC", coating_status="resolved",
        coating_confidence=0.9, review_status="pending",
    )
    parser.extracted_models = [ExtractedLensModel(name="Aquila", power_ranges=[pr])]
    parser.save_extractions_to_db(cat.id, db)

    ext = db.query(models.CatalogExtraction).one()
    assert ext.extracted_design == "Free Form"
    assert ext.extracted_color_variant == "Transmatic/G/B"
    assert ext.extracted_market_scope == "Egypt"
    assert ext.extracted_coating == "HMC"
    assert ext.coating_extraction_status == models.CoatingExtractionStatus.RESOLVED
    assert ext.coating_confidence == 0.9
    assert ext.status == "pending"
    assert ext.extracted_price == 1234.56


def test_P2_needs_review_status_persists(parser, db):
    company = models.Company(name="ACME"); db.add(company); db.commit(); db.refresh(company)
    cat = models.Catalog(company_id=company.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    pr = ExtractedPowerRange(sph_min=0.0, sph_max=0.0, availability="stock",
                             price=100.0, coating_status="not_found",
                             review_status="needs_review",
                             review_reasons=["STOCK without PowerRange", "coating not_found"])
    parser.extracted_models = [ExtractedLensModel(name="X", power_ranges=[pr])]
    parser.save_extractions_to_db(cat.id, db)
    ext = db.query(models.CatalogExtraction).one()
    assert ext.status == "needs_review"
    assert ext.coating_extraction_status == models.CoatingExtractionStatus.NOT_FOUND
    assert "STOCK without PowerRange" in (ext.review_notes or "")


# ===========================================================================
# Q. a clean price is never altered by context enrichment
# ===========================================================================
def test_Q_clean_price_untouched_by_enrichment(parser):
    tbl = [["SPH", "CYL", "Price", "Design", "Color"],
           ["-6.00 to 0.00", "-2.00", "1234.56", "Free Form", "Clear"]]
    ctx = _ctx(availability="stock", market="Egypt", design_variant="High Definition")
    r = _rows(parser, tbl, ctx)[0]
    assert r.price == 1234.56           # exact, unchanged
    assert r.market_scope == "Egypt"    # enrichment happened
    assert r.design_variant == "Free Form"   # row cell wins over context


# ===========================================================================
# R. unresolved / corrupt price stays needs_review
# ===========================================================================
def test_R_corrupt_price_needs_review(parser):
    tbl = [["SPH", "CYL", "Price"],
           ["-6.00 to 0.00", "-2.00", "12##.@@"]]
    r = _rows(parser, tbl)[0]
    assert r.price is None
    assert r.review_status == "needs_review"
    assert "unresolved price cell" in r.review_reasons


def test_R2_clean_currency_price_is_accepted(parser):
    # coating column present + explicit blank -> only the price is under test here
    tbl = [["SPH", "CYL", "Price", "Coating"],
           ["-6.00 to 0.00", "-2.00", "EGP 1,250.00", "-"]]
    r = _rows(parser, tbl)[0]
    assert r.price == 1250.0
    assert "unresolved price cell" not in r.review_reasons
    assert r.review_status == "pending"


# ===========================================================================
# tier / Egypt-style banded table (item 9)
# ===========================================================================
def test_tier_bands_stay_distinct(parser):
    tbl = [["Total Power", "Cyl2", "Cyl4"],
           ["-6.00 to +6.00", "2500", "5500"]]
    rows = _rows(parser, tbl)
    assert len(rows) == 2
    bands = sorted((r.cyl_min, r.price) for r in rows)
    assert bands == [(-4.0, 5500.0), (-2.0, 2500.0)]


# ===========================================================================
# geometry term still goes to design_type, not design_variant
# ===========================================================================
def test_geometry_term_goes_to_design_type(parser):
    tbl = [["SPH", "CYL", "Price", "Design"],
           ["-6.00 to 0.00", "-2.00", "100", "Aspherical"]]
    r = _rows(parser, tbl)[0]
    assert r.design_type == "aspherical"
    assert r.is_aspherical is True
    assert r.design_variant is None


# ===========================================================================
# Item 10 - real-PDF extraction blockers (structure-level, synthetic geometry)
# ===========================================================================
from app.pdf_hybrid_parser import _dedouble, _clean  # noqa: E402


def test_10A_line_result_headers_only_triggers_text_fallback(parser):
    frag = [["Index", "Coating", "Design", "Color"], ["- - (Price)", "", ""]]
    assert parser._matrix_is_useful(frag) is False
    good = [["Index", "Price"], ["1.5", "700"], ["1.56", "900"]]
    assert parser._matrix_is_useful(good) is True


def test_10B_text_position_matrix_produces_commercial_rows(parser):
    hdr = [["Index", "Coating", "Design", "Color", "Sph", "Cyl", "Price"]]
    matrix = hdr + [
        ["1.53", "Astro", "Spheric", "Clear", "0.00 To -6.00", "-2.00", "2500"],
        ["1.56", "Astro+", "Aspheric", "Clear", "0.00 To -4.00", "-2.00", "4500"],
    ]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="stock", market="X"))
    assert len(rows) == 2
    assert {r.price for r in rows} == {2500.0, 4500.0}
    assert rows[0].sph_min == -6.0 and rows[0].has_range


def test_10C_dedup_across_strategies(parser):
    m = [["Index", "Price"], ["1.5", "700"], ["1.56", "900"]]
    cands = [(10, {}, m[:1], m), (11, {}, m[:1], [[_clean(c) for c in r] for r in m])]
    best = {}
    for score, ov, hdr, mat in cands:
        sig = (parser._sig(hdr), parser._sig(mat[1:]))
        if sig not in best or score > best[sig][0]:
            best[sig] = (score, ov, hdr, mat)
    assert len(best) == 1


def test_10D_doubled_header_normalized_by_geometry(parser):
    assert _dedouble("IInnddeexx") == "Index"
    assert _dedouble("AAssttrroo") == "Astro"
    assert _dedouble("CCoolloorr") == "Color"
    assert (parser._classify_design("HHiigghh DDeefifinnnnaattiioonn") == "High Definition"
            or parser._classify_design("High Deﬁnnation") == "High Definition")


def test_10E_legitimate_repeats_not_collapsed(parser):
    assert _dedouble("Free") == "Free"
    assert _dedouble("1000") == "1000"
    assert _dedouble("Premium") == "Premium"
    assert parser._extract_price("1000") == 1000.0
    assert parser._extract_price("7700") == 7700.0


def test_10F_two_numeric_columns_stay_two_values(parser):
    hdr = [["Index", "Coating", "Color", "Free Form", "High Definition"]]
    matrix = hdr + [["1.5", "Astro", "Clear", "2500", "3500"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert {(r.design_variant, r.price) for r in rows} == {
        ("Free Form", 2500.0), ("High Definition", 3500.0)}


def test_10G_unrecoverable_numeric_cell_is_needs_review(parser):
    hdr = [["Index", "Coating", "Color", "Free Form"]]
    matrix = hdr + [["1.5", "Astro", "Clear", "21050000"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert len(rows) == 1
    assert rows[0].price is None
    assert rows[0].review_status == "needs_review"
    assert any("price" in x for x in rows[0].review_reasons)


def test_10H_marketing_heading_cannot_be_family(parser):
    for junk in ("Surface Design", "Designs", "Coating Technology", "Comparison",
                 "CLARITY", "Hazardous", "Index", "Color", "EMI", "HD"):
        assert parser._looks_like_family(junk) is False
    assert parser._extract_model_name("Optical Performance Comparison") is None
    assert parser._extract_model_name("Lens : Aquila") == "Aquila"


def test_10I_portfolio_relation_uniquely_resolves(parser):
    ctx = ParserContext(availability="rx", category="progressive", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Falcon", "availability": "stock", "category": "single_vision",
         "market": "Egypt", "terms": {"emi"}},
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro", "core"}},
    ]
    assert parser._resolve_family(ctx, {"astro"}) == "Aquila"


def test_10J_ambiguous_relation_needs_review(parser):
    ctx = ParserContext(availability="rx", category="progressive", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
        {"family": "Falcon", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
    ]
    rows = [ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=100.0)]
    assert parser._assign_family(ctx, rows) == parser.UNRESOLVED_FAMILY
    assert rows[0].review_status == "needs_review"
    assert "ambiguous/unresolved product family" in rows[0].review_reasons


def test_10K_tier_total_power_cyl_bands_independent(parser):
    hdr = [["Index", "Coating", "Design", "Color", "Total Power", "Cyl 2", "Cyl4"]]
    matrix = hdr + [["1.5", "Astro", "Spheric", "Clear", "4.00", "700", "800"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="stock", market="Egypt"))
    assert len(rows) == 2
    assert sorted((r.cyl_min, r.price) for r in rows) == [(-4.0, 800.0), (-2.0, 700.0)]
    assert all(r.has_range for r in rows)


def test_10L_sph_cyl_price_bands_independent(parser):
    hdr = [["Index", "Coating", "Color", "Sph", "Cyl", "Price", "Sph", "Cyl", "Price"]]
    matrix = hdr + [["1.74", "Astro", "Clear", "0.00 To -6.00", "-2.00", "5500",
                     "0.00 to +4.00", "-2.00", "6000"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="stock", market="X"))
    assert len(rows) == 2
    assert sorted(r.price for r in rows) == [5500.0, 6000.0]
    assert {r.notes for r in rows} == {"minus", "plus"}


def test_10M_multi_design_rx_columns_separate_rows(parser):
    hdr = [["Index", "Coating", "Color", "Free Form", "High Definition"]]
    matrix = hdr + [["1.61", "Astro", "Transmatic/G/B", "8000", "9000"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert {(r.design_variant, r.price) for r in rows} == {
        ("Free Form", 8000.0), ("High Definition", 9000.0)}
    assert all(r.color_variant == "Transmatic/G/B" for r in rows)
    assert all(r.design_type == "spherical" for r in rows)


def test_10N_progressive_columns_separate(parser):
    hdr = [["Index", "Coating", "Color", "Core (*)", "Advance (**)", "Premium (***)"]]
    matrix = hdr + [["1.5", "Astro", "Clear", "4000", "5500", "7500"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert {(r.design_variant, r.price) for r in rows} == {
        ("Core", 4000.0), ("Advance", 5500.0), ("Premium", 7500.0)}


def test_10N_progressive_dash_is_unavailable(parser):
    hdr = [["Index", "Coating", "Color", "Core (*)", "Advance (**)", "Premium (***)"]]
    matrix = hdr + [["1.53", "Astro", "Clear", "-", "8000", "10000"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert {r.design_variant for r in rows} == {"Advance", "Premium"}


def test_10O_bifocal_columns_separate(parser):
    hdr = [["Index", "Coating", "Color", "D Type", "Kt Type"]]
    matrix = hdr + [["1.5", "Astro", "Clear", "2500", "2500"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert {r.design_variant for r in rows} == {"D Type", "KT Type"}
    assert all(r.price == 2500.0 for r in rows)


def test_10P_addon_block_same_page_zero_base_rows(parser):
    hdr = [["Index", "Coating", "Color", "Free Form"]]
    matrix = hdr + [
        ["1.5", "Astro", "Clear", "2500"],
        ["Hi Power", "", "", "1000"],
        ["Tinting", "", "", "300"],
        ["Blue Cut", "", "", "1000"],
        ["Mirror", "", "", "1000"],
    ]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert len(rows) == 1 and rows[0].price == 2500.0


def test_10Q_numeric_treatment_price_not_color(parser):
    hdr = [["Index", "Coating", "Color", "Free Form"]]
    matrix = hdr + [["1.5", "Astro", "300", "2500"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert rows[0].color_variant is None


def test_10R_rx_without_range_stays_valid(parser):
    hdr = [["Index", "Coating", "Color", "Free Form"]]
    matrix = hdr + [["1.5", "Astro", "Clear", "2500"]]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="rx", market="X"))
    assert len(rows) == 1 and rows[0].has_range is False
    assert "STOCK without PowerRange" not in rows[0].review_reasons
    assert rows[0].review_status == "pending"


_PIXEL = os.path.join(os.path.expanduser("~"), "Downloads", "pixel_phase4_test.pdf")


@pytest.mark.skipif(not os.path.exists(_PIXEL), reason="real PIXEL catalog not present")
def test_real_catalog_produces_clean_commercial_rows():
    import re as _re
    parser = PDFHybridParser(use_vision=False)
    models = parser.parse_pdf(_PIXEL)
    rows = [pr for m in models for pr in m.power_ranges]
    assert len(rows) > 40
    for r in rows:
        if r.color_variant:
            assert not _re.fullmatch(r"[0-9.]+", str(r.color_variant))
            assert not any(t in str(r.color_variant).lower()
                           for t in ("hi power", "tinting", "blue cut", "mirror"))
    assert all(r.design_type in ("spherical", "aspherical", "double_aspherical") for r in rows)
    dvs = {r.design_variant for r in rows if r.design_variant}
    assert {"Free Form", "High Definition"} & dvs
    assert {"Core", "Advance", "Premium"} & dvs
    assert any("egypt" in (r.market_scope or "").lower() for r in rows)
    for r in rows:
        if r.price is not None:
            assert r.price < 100000
    for m in models:
        assert m.name.lower() not in ("comparison", "clarity", "hazardous", "designs")


# ===========================================================================
# Family resolution - geometry binding + real catalog (Phase 4 fix)
# ===========================================================================
def test_family_column_binds_to_offset_relation_row(parser):
    """A family label in its own x-column, vertically offset from the relation
    cells, is bound to the relation row nearest in y."""
    class _W:
        pass

    def w(text, x0, top):
        return {"text": text, "x0": float(x0), "x1": float(x0 + 8 * len(text)),
                "top": float(top), "bottom": float(top + 10)}

    words = [
        w("Portfolio", 40, 10),
        w("Aquila", 210, 100),                       # family column (x~210)
        w("Stock", 70, 116), w("Lens", 110, 116),    # relation row, offset +16 in y
        w("Single", 175, 116), w("Vision", 220, 116),
        w("Astro", 300, 116), w("Egypt", 490, 116),
        w("Lens", 210, 132),                         # 2nd line of the family label
        w("Falcon", 210, 180),                       # family column
        w("Rx", 80, 196), w("Lens", 100, 196),
        w("Progressive", 180, 196),
        w("Core", 300, 196), w("Outside", 470, 196), w("Egypt", 500, 196),
        w("Lens", 210, 212),
    ]

    class FakePage:
        chars = []
        def extract_words(self, **k):
            return words

    parser._dedup_overprint_words = lambda page: words        # bypass char rebuild
    ctx = ParserContext()
    parser._ingest_relation_page(ctx, FakePage(), "Product Portfolio Overview")
    fams = {(r["family"], r["availability"], r["category"]) for r in ctx.relations}
    assert ("Aquila", "stock", "single_vision") in fams
    assert ("Falcon", "rx", "progressive") in fams


@pytest.mark.skipif(not os.path.exists(_PIXEL), reason="real PIXEL catalog not present")
def test_real_catalog_family_resolution():
    parser = PDFHybridParser(use_vision=False)
    models = parser.parse_pdf(_PIXEL)
    names = [m.name for m in models]
    # a pricing-section heading must NEVER become a model name
    for n in names:
        assert not n.lower().startswith(("finished", "rx ", "rx,", "retail"))
        assert "single vision" not in n.lower()
    rows = [(m.name, pr) for m in models for pr in m.power_ranges]
    resolved = [r for n, r in rows if n != parser.UNRESOLVED_FAMILY]
    unresolved = [r for n, r in rows if n == parser.UNRESOLVED_FAMILY]
    assert len(resolved) > 100                       # most rows carry a real family
    # every unresolved-family row is needs_review with the right reason
    for r in unresolved:
        assert r.review_status == "needs_review"
        assert "ambiguous/unresolved product family" in r.review_reasons
    # families came from portfolio evidence, not price
    real_fams = {n for n in names if n != parser.UNRESOLVED_FAMILY}
    assert len(real_fams) >= 1 and all(len(f) <= 24 for f in real_fams)


# ===========================================================================
# Human-reviewed family override for the PIXEL catalog bifocal rows
# (catalog-specific, applied via modified_data - NOT a generic parser rule)
# ===========================================================================
from app import crud  # noqa: E402


def _company_catalog(db):
    co = models.Company(name="ACME")
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return co, cat


def _bifocal_ext(db, cat, name=None):
    e = models.CatalogExtraction(
        catalog_id=cat.id,
        extracted_name=name or models.UNRESOLVED_FAMILY_NAME,
        extracted_material="CR39", extracted_index=1.5,
        extracted_availability="rx", extracted_price=2500.0,
        extracted_design="D Type",
        coating_extraction_status=models.CoatingExtractionStatus.EXPLICIT_NONE,
        modified_data={"design_variant": "D Type"},   # parser overlay already present
        review_notes="ambiguous/unresolved product family",
        status="needs_review",
    )
    db.add(e); db.commit(); db.refresh(e)
    return e


@pytest.mark.skipif(not os.path.exists(_PIXEL), reason="real PIXEL catalog not present")
def test_override_1_parser_alone_still_unresolved_for_bifocal():
    parser = PDFHybridParser(use_vision=False)
    models_ = parser.parse_pdf(_PIXEL)
    bifocal = [m for m in models_ if m.category == "bifocal"]
    assert bifocal, "expected a parsed bifocal section"
    for m in bifocal:
        assert m.name == parser.UNRESOLVED_FAMILY          # parser never infers it
        for pr in m.power_ranges:
            assert pr.review_status == "needs_review"
            assert "ambiguous/unresolved product family" in pr.review_reasons


def test_override_2_human_override_sets_family_with_provenance(db):
    _, cat = _company_catalog(db)
    e = _bifocal_ext(db, cat)
    out = crud.apply_family_review_override(db, e.id, "Pixel", reviewed_by="catalog owner")
    md = out.modified_data
    assert md["name"] == "Pixel"
    assert md["family_source"] == "human_review"          # provenance: not parser inference
    assert md["family_reviewed_by"] == "catalog owner"
    assert "family_reviewed_at" in md
    assert md["design_variant"] == "D Type"               # parser overlay preserved
    assert "Pixel" in (out.review_notes or "") and "human review" in out.review_notes
    # the stored parser column is untouched
    assert e.extracted_name == models.UNRESOLVED_FAMILY_NAME


def test_override_3_no_generic_bifocal_or_catalog_rule_added(db):
    # a bifocal section with NO relation evidence still resolves to unresolved
    parser = PDFHybridParser(use_vision=False)
    ctx = ParserContext(availability="rx", category="bifocal", market="Out Of Egypt")
    ctx.relations = [
        {"family": "Aquila", "availability": "rx", "category": "progressive",
         "market": "Out Of Egypt", "terms": {"astro"}},
    ]
    rows = [ExtractedPowerRange(sph_min=0.0, sph_max=0.0, price=2500.0, design_variant="D Type")]
    assert parser._assign_family(ctx, rows) == parser.UNRESOLVED_FAMILY
    assert "ambiguous/unresolved product family" in rows[0].review_reasons
    # override helper never hardcodes a family
    import inspect
    src = inspect.getsource(crud.apply_family_review_override)
    assert "Pixel" not in src and "bifocal" not in src.lower()


def test_override_4_bulk_confirm_prep_reads_the_override(db):
    _, cat = _company_catalog(db)

    # (a) without the override: prep blocks on unresolved family
    e1 = _bifocal_ext(db, cat)
    e1.status = "confirmed"; db.commit()
    res = crud._prepare_extraction_row(db.get(models.CatalogExtraction, e1.id))
    assert "errors" in res
    assert any("unresolved product family" in x for x in res["errors"])

    # (b) with the human override: prep resolves family = Pixel, no family error
    e2 = _bifocal_ext(db, cat)
    crud.apply_family_review_override(db, e2.id, "Pixel", reviewed_by="catalog owner")
    e2.status = "confirmed"; db.commit()
    res = crud._prepare_extraction_row(db.get(models.CatalogExtraction, e2.id))
    assert "row" in res, res
    assert res["row"]["name"] == "Pixel"


# ===========================================================================
# Fabricated-RX-PowerRange defect fix (found by real E2E smoke test)
# ===========================================================================
from decimal import Decimal as _D
from app import crud as _crud
from app.lens_matcher import lens_matcher as _matcher


def _company_catalog(db):
    co = models.Company(name="RXFIX Co", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    return co, cat


def _persist_via_parser(parser, db, cat, pr, name="RxFam", category="progressive"):
    parser.extracted_models = [
        ExtractedLensModel(name=name, category=category, power_ranges=[pr])
    ]
    parser.save_extractions_to_db(cat.id, db)
    return _crud.get_extractions_by_catalog(db, cat.id)[-1]


def _rx_norange_pr():
    # exactly what the real parser emits for a clean rangeless RX Progressive row:
    # has_range=False, dataclass cyl fallback -10/0 still on the object
    return ExtractedPowerRange(
        sph_min=0.0, sph_max=0.0, availability="rx", price=4000.0,
        index_value=1.5, design_variant="Core", color_variant="Clear",
        market_scope="Out Of Egypt", coating="Astro", coating_status="resolved",
        coating_confidence=0.9, has_range=False, review_status="pending",
    )


def test_rxfix_A_parser_persists_none_ranges_for_no_range_row(parser, db):
    _, cat = _company_catalog(db)
    ext = _persist_via_parser(parser, db, cat, _rx_norange_pr())
    assert ext.sph_min is None and ext.sph_max is None
    assert ext.cyl_min is None and ext.cyl_max is None
    assert ext.add_min is None and ext.add_max is None
    assert ext.extracted_availability == "rx"
    assert ext.extracted_price == 4000.0


def test_rxfix_B_prepare_row_no_range_no_power_scope(parser, db):
    _, cat = _company_catalog(db)
    ext = _persist_via_parser(parser, db, cat, _rx_norange_pr())
    ext.status = "confirmed"
    db.commit()
    res = _crud._prepare_extraction_row(db.get(models.CatalogExtraction, ext.id))
    assert "row" in res, res
    assert res["row"]["has_range"] is False
    assert res["row"]["power_scope"] is None


def test_rxfix_C_bulk_confirm_rx_zero_power_ranges(parser, db):
    _, cat = _company_catalog(db)
    ext = _persist_via_parser(parser, db, cat, _rx_norange_pr())
    _crud.confirm_extraction(db, ext.id, "qa")
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    vps = db.query(models.VariantPricing).all()
    assert len(vps) == 1
    vp = vps[0]
    assert vp.availability == models.PricingAvailability.RX
    assert vp.power_scope is None
    assert vp.price_pair == _D("4000.00")
    assert db.query(models.PowerRange).filter_by(pricing_id=vp.id).count() == 0


def test_rxfix_D_matcher_returns_rx_for_nonzero_sph(parser, db):
    company, cat = _company_catalog(db)
    ext = _persist_via_parser(parser, db, cat, _rx_norange_pr())
    _crud.confirm_extraction(db, ext.id, "qa")
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    vp = db.query(models.VariantPricing).one()

    p = models.Prescription(od_sph_original=-3.0, os_sph_original=-3.0,
        od_sph=-3.0, os_sph=-3.0, od_cyl_original=-1.0, os_cyl_original=-1.0,
        od_cyl=-1.0, os_cyl=-1.0, od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
    db.add(p); db.commit(); db.refresh(p)
    results, sc, rc, *_ = _matcher.match_lenses(db, p, None, True, True)
    hit = [r for r in results if r.source_pricing_id == vp.id]
    assert hit, "RX candidate missing for a non-zero SPH prescription"
    h = hit[0]
    assert h.availability == "rx"
    assert h.power_range is None
    assert h.price_pair == _D("4000.00")
    assert h.design_variant == "Core" and h.color_variant == "Clear"
    assert h.market_scope == "Out Of Egypt"


def test_rxfix_E_stock_without_range_still_blocks(parser, db):
    _, cat = _company_catalog(db)
    stock_pr = ExtractedPowerRange(
        sph_min=0.0, sph_max=0.0, availability="stock", price=700.0, index_value=1.5,
        color_variant="Clear", market_scope="Egypt", coating="Astro",
        coating_status="resolved", coating_confidence=0.9, has_range=False,
        review_status="pending",
    )
    ext = _persist_via_parser(parser, db, cat, stock_pr, name="StockFam",
                              category="single_vision")
    _crud.confirm_extraction(db, ext.id, "qa")
    with pytest.raises(_crud.CommercialValidationError) as exc:
        _crud.confirm_catalog_commercial(db, cat.id, "admin")
    assert any("STOCK requires PowerRange" in e for e in exc.value.errors)
    assert db.query(models.VariantPricing).count() == 0


def test_rxfix_F_explicit_rx_range_still_constrains(parser, db):
    _, cat = _company_catalog(db)
    rx_ranged = ExtractedPowerRange(
        sph_min=-6.0, sph_max=-2.0, cyl_min=-2.0, cyl_max=0.0,
        availability="rx", price=5500.0, index_value=1.6, design_variant="Premium",
        color_variant="Clear", market_scope="Out Of Egypt", coating="Astro",
        coating_status="resolved", coating_confidence=0.9, has_range=True,
        review_status="pending",
    )
    ext = _persist_via_parser(parser, db, cat, rx_ranged, name="RxRanged")
    # explicit range survives the parser -> extraction boundary
    assert ext.sph_min == -6.0 and ext.sph_max == -2.0
    _crud.confirm_extraction(db, ext.id, "qa")
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    vp = db.query(models.VariantPricing).one()
    assert vp.power_scope is not None
    prs = db.query(models.PowerRange).filter_by(pricing_id=vp.id).all()
    assert len(prs) == 1 and prs[0].sph_min == -6.0 and prs[0].sph_max == -2.0

    def _presc(sph):
        p = models.Prescription(od_sph_original=sph, os_sph_original=sph, od_sph=sph,
            os_sph=sph, od_cyl_original=-1.0, os_cyl_original=-1.0, od_cyl=-1.0,
            os_cyl=-1.0, od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(p); db.commit(); db.refresh(p); return p

    inside = _matcher.match_lenses(db, _presc(-4.0), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in inside)
    outside = _matcher.match_lenses(db, _presc(3.0), None, True, True)[0]
    assert not any(r.source_pricing_id == vp.id for r in outside)


# ===========================================================================
# LensModel category-collapse defect fix
# "Pixel" Single Vision and "Pixel" Progressive must be two distinct LensModels
# ===========================================================================
from app import schemas as _schemas


def _stock_ranged_pr(index=1.5, price=700.0, design_variant="Core"):
    return ExtractedPowerRange(
        sph_min=-6.0, sph_max=6.0, cyl_min=-4.0, cyl_max=0.0,
        availability="stock", price=price, index_value=index,
        design_variant=design_variant, color_variant="Clear",
        market_scope="Egypt", coating="Astro", coating_status="resolved",
        coating_confidence=0.9, has_range=True, review_status="pending",
    )


def _rx_norange_pr_named(index=1.5, price=4000.0, design_variant="Core"):
    return ExtractedPowerRange(
        sph_min=0.0, sph_max=0.0, availability="rx", price=price,
        index_value=index, design_variant=design_variant, color_variant="Clear",
        market_scope="Out Of Egypt", coating="Astro", coating_status="resolved",
        coating_confidence=0.9, has_range=False, review_status="pending",
    )


def _confirm_all(db, cat, reviewer="qa", admin="admin"):
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        _crud.confirm_extraction(db, e.id, reviewer)
    return _crud.confirm_catalog_commercial(db, cat.id, admin)


def _presc(db, sph=-2.0, cyl=-1.0, add=0.0):
    p = models.Prescription(
        od_sph_original=sph, os_sph_original=sph, od_sph=sph, os_sph=sph,
        od_cyl_original=cyl, os_cyl_original=cyl, od_cyl=cyl, os_cyl=cyl,
        od_axis=0, os_axis=0, od_add=add, os_add=add,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def test_catfix_A_same_name_two_categories_two_models(parser, db):
    company, cat = _company_catalog(db)
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(), name="Pixel",
                        category="single_vision")
    _persist_via_parser(parser, db, cat, _rx_norange_pr_named(), name="Pixel",
                        category="progressive")
    _confirm_all(db, cat)

    pixels = (db.query(models.LensModel)
              .filter(models.LensModel.company_id == company.id,
                      models.LensModel.name == "Pixel").all())
    assert len(pixels) == 2, [(m.id, m.name, m.category) for m in pixels]
    assert {m.name for m in pixels} == {"Pixel"}
    assert {m.category for m in pixels} == {
        models.LensCategory.SINGLE_VISION, models.LensCategory.PROGRESSIVE
    }
    assert pixels[0].id != pixels[1].id


def test_catfix_B_pricing_points_to_correct_model_category(parser, db):
    company, cat = _company_catalog(db)
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(price=700.0), name="Pixel",
                        category="single_vision")
    _persist_via_parser(parser, db, cat, _rx_norange_pr_named(price=4000.0), name="Pixel",
                        category="progressive")
    _confirm_all(db, cat)

    by_cat = {}
    for vp in db.query(models.VariantPricing).all():
        lm = vp.variant.lens_model
        by_cat[lm.category] = (vp, lm)

    sv_vp, sv_lm = by_cat[models.LensCategory.SINGLE_VISION]
    pr_vp, pr_lm = by_cat[models.LensCategory.PROGRESSIVE]
    assert sv_lm.name == "Pixel" and pr_lm.name == "Pixel"
    assert sv_lm.id != pr_lm.id
    assert sv_vp.availability == models.PricingAvailability.STOCK
    assert sv_vp.price_pair == _D("700.00")
    assert pr_vp.availability == models.PricingAvailability.RX
    assert pr_vp.price_pair == _D("4000.00")
    assert pr_vp.power_scope is None
    assert db.query(models.PowerRange).filter_by(pricing_id=pr_vp.id).count() == 0


def test_catfix_C_sequential_catalogs_keep_both_models(parser, db):
    company, cat1 = _company_catalog(db)
    _persist_via_parser(parser, db, cat1, _stock_ranged_pr(), name="Pixel",
                        category="single_vision")
    _confirm_all(db, cat1)
    sv = (db.query(models.LensModel)
          .filter_by(company_id=company.id, name="Pixel").one())
    sv_id, sv_cat = sv.id, sv.category
    assert sv_cat == models.LensCategory.SINGLE_VISION

    cat2 = models.Catalog(company_id=company.id, filename="c2.pdf", file_path="/x2",
                          status=models.CatalogStatus.DRAFT)
    db.add(cat2); db.commit(); db.refresh(cat2)
    _persist_via_parser(parser, db, cat2, _rx_norange_pr_named(), name="Pixel",
                        category="progressive")
    _confirm_all(db, cat2)

    pixels = (db.query(models.LensModel)
              .filter_by(company_id=company.id, name="Pixel").all())
    assert len(pixels) == 2
    sv_after = db.get(models.LensModel, sv_id)
    assert sv_after.id == sv_id
    assert sv_after.category == models.LensCategory.SINGLE_VISION
    assert {m.category for m in pixels} == {
        models.LensCategory.SINGLE_VISION, models.LensCategory.PROGRESSIVE
    }


def test_catfix_D_same_name_category_diff_index_one_model(parser, db):
    company, cat = _company_catalog(db)
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(index=1.5, price=700.0),
                        name="Pixel", category="single_vision")
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(index=1.6, price=900.0),
                        name="Pixel", category="single_vision")
    _confirm_all(db, cat)

    pixels = (db.query(models.LensModel)
              .filter_by(company_id=company.id, name="Pixel").all())
    assert len(pixels) == 1, [(m.id, m.category) for m in pixels]
    variants = db.query(models.LensVariant).filter_by(lens_model_id=pixels[0].id).all()
    assert len(variants) == 2
    assert {round(v.index_value, 2) for v in variants} == {1.5, 1.6}
    assert db.query(models.VariantPricing).count() == 2


def test_catfix_E_exact_duplicate_including_category_rejected(parser, db):
    company, cat = _company_catalog(db)
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(index=1.5, price=700.0),
                        name="Pixel", category="single_vision")
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(index=1.5, price=700.0),
                        name="Pixel", category="single_vision")
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        _crud.confirm_extraction(db, e.id, "qa")
    with pytest.raises(_crud.CommercialValidationError) as exc:
        _crud.confirm_catalog_commercial(db, cat.id, "admin")
    assert any("duplicate commercial identity" in e for e in exc.value.errors)
    assert db.query(models.VariantPricing).count() == 0


def test_catfix_F_matcher_category_filter_splits_pixel(parser, db):
    company, cat = _company_catalog(db)
    _persist_via_parser(parser, db, cat, _stock_ranged_pr(price=700.0), name="Pixel",
                        category="single_vision")
    _persist_via_parser(parser, db, cat, _rx_norange_pr_named(price=4000.0), name="Pixel",
                        category="progressive")
    _confirm_all(db, cat)

    p = _presc(db, sph=-2.0, cyl=-1.0)

    sv_res = _matcher.match_lenses(
        db, p, _schemas.LensFilters(category=models.LensCategory.SINGLE_VISION),
        True, True)[0]
    assert sv_res, "expected a Single Vision match"
    assert {r.lens_model.category for r in sv_res} == {models.LensCategory.SINGLE_VISION}
    assert all(r.availability == "stock" for r in sv_res)
    assert all(r.price_pair == _D("700.00") for r in sv_res)

    pr_res = _matcher.match_lenses(
        db, p, _schemas.LensFilters(category=models.LensCategory.PROGRESSIVE),
        True, True)[0]
    assert pr_res, "expected a Progressive match"
    assert {r.lens_model.category for r in pr_res} == {models.LensCategory.PROGRESSIVE}
    assert all(r.availability == "rx" for r in pr_res)
    assert all(r.price_pair == _D("4000.00") for r in pr_res)


# ===========================================================================
# Generic merged-cell ruled table + per-price subgroup reconstruction
# (Type | Coating | Price | Stock Range, merged identity, dotted subgroup rule)
# ===========================================================================
_HOYA = os.path.join(os.path.expanduser("~"), "Downloads", "Hoya_Price_List_2025.pdf")

_H4 = ["Type", "Coating", "Price", "Stock Range"]


def _sub(parser, *, ident, prices, ranges, grp_ys=(), sub_ys=(), y_top=0.0, y_bot=100.0):
    return parser._build_price_subgroups(
        list(_H4), y_top, y_bot, list(ident), list(prices), list(ranges),
        sorted(grp_ys), sorted(sub_ys),
    )


def _rowset(matrix):
    return {tuple(r) for r in matrix[1:]}


# -- A. sparse merged-table structural trigger -------------------------------
def test_mg_A_sparse_merged_grid_detected(parser):
    sparse = [["Type", "Coating", "Price", "Stock Range"],
              [None, "", "1350", None], [None, None, "1450", None],
              [None, "", "3300", None]]
    assert parser._is_sparse_merged_grid(sparse, sparse[0]) is True


def test_mg_K_normal_full_table_not_triggered(parser):
    full = [["Index", "Coating", "Price"],
            ["1.5", "Astro", "700"], ["1.56", "Astro+", "900"]]
    assert parser._is_sparse_merged_grid(full, full[0]) is False


# -- B. solid full-width rule -> new Type/Coating group ---------------------
def test_mg_B_solid_full_width_starts_new_group(parser):
    subs = _sub(
        parser,
        ident=[(10, "Alpha 1.5"), (15, "CoatA"), (55, "Beta 1.6"), (60, "CoatB")],
        prices=[(20, "700"), (70, "900")],
        ranges=[(25, "r1"), (75, "r2")],
        grp_ys=[50],
    )
    assert len(subs) == 2
    a, b = subs[0][2], subs[1][2]
    assert a[1][0] == "Alpha 1.5" and a[1][1] == "CoatA" and a[1][2] == "700"
    assert b[1][0] == "Beta 1.6" and b[1][1] == "CoatB" and b[1][2] == "900"
    # ranges did not cross the group boundary
    assert _rowset(a) == {("Alpha 1.5", "CoatA", "700", "r1")}
    assert _rowset(b) == {("Beta 1.6", "CoatB", "900", "r2")}


# -- C/D/E/F/G. dotted partial rule -> price subgroups --------------------
def _two_price_dotted(parser):
    return _sub(
        parser,
        ident=[(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        prices=[(15, "1350"), (60, "1450")],
        ranges=[(10, "Ra"), (25, "Rb"), (45, "Rc"), (55, "Rd")],
        sub_ys=[40],
    )


def test_mg_C_dotted_partial_creates_subgroup(parser):
    subs = _two_price_dotted(parser)
    assert len(subs) == 2
    assert {s[2][1][2] for s in subs} == {"1350", "1450"}


def test_mg_D_same_type_coating_inherited_across_prices(parser):
    subs = _two_price_dotted(parser)
    for ov, hdr, mat in subs:
        for row in mat[1:]:
            assert row[0] == "Hilux 1.5" and row[1] == "Hi Vision Aqua"


def test_mg_E_price_1350_owns_only_its_ranges(parser):
    subs = _two_price_dotted(parser)
    s1350 = next(m for _, _, m in subs if m[1][2] == "1350")
    assert {r[3] for r in s1350[1:]} == {"Ra", "Rb"}


def test_mg_F_price_1450_owns_only_its_ranges(parser):
    subs = _two_price_dotted(parser)
    s1450 = next(m for _, _, m in subs if m[1][2] == "1450")
    assert {r[3] for r in s1450[1:]} == {"Rc", "Rd"}


def test_mg_G_range_sets_disjoint(parser):
    subs = _two_price_dotted(parser)
    a = {r[3] for r in subs[0][2][1:]}
    b = {r[3] for r in subs[1][2][1:]}
    assert a and b and a.isdisjoint(b)


# -- H. no dotted rule, multiple prices, clean geometric split ------------
def test_mg_H_no_separator_multiple_prices_still_split(parser):
    subs = _sub(
        parser,
        ident=[(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        prices=[(15, "1350"), (60, "1450")],
        ranges=[(10, "a"), (20, "b"), (50, "c"), (70, "d")],  # clean around mid 37.5
    )
    assert len(subs) == 2
    got = {m[1][2]: {r[3] for r in m[1:]} for _, _, m in subs}
    assert got["1350"] == {"a", "b"} and got["1450"] == {"c", "d"}
    assert got["1350"].isdisjoint(got["1450"])
    assert all(not ov.get("review_reason") for ov, _, _ in subs)


# -- I. multiple prices, boundary unprovable -> needs_review, no guessing --
def test_mg_I_unprovable_split_flags_review_never_merges(parser):
    subs = _sub(
        parser,
        ident=[(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        prices=[(15, "1350"), (60, "1450")],
        ranges=[(10, "a"), (37, "amb"), (55, "d")],  # 'amb' sits on the 37.5 midline
    )
    assert len(subs) == 2                       # never merged into one price
    assert all(ov.get("review_reason") for ov, _, _ in subs)
    allr = [r[3] for _, _, m in subs for r in m[1:]]
    assert len(allr) == len(set(allr))         # no range assigned to both prices


# -- J. blank continuation inherits identity + price ---------------------
def test_mg_J_blank_continuation_inherits(parser):
    matrix = [list(_H4),
              ["Hilux 1.5", "Hi Vision Aqua", "1350", "0.00 to -4.00"],
              ["", "", "", "0.00 to -3.00"]]
    rows = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))
    assert len(rows) == 2
    assert all(r.price == 1350.0 for r in rows)
    assert all(r.model_hint == "Hilux" for r in rows)
    assert all(r.coating == "Hi Vision Aqua" for r in rows)
    assert rows[0].sph_min == -4.0 and rows[1].sph_min == -3.0   # bare ranges parse


# -- K covered above (test_mg_K_normal_full_table_not_triggered) ---------
def test_mg_K_normal_section_matrix_behaviour_unchanged(parser):
    hdr = [["Index", "Coating", "Design", "Color", "Sph", "Cyl", "Price"]]
    matrix = hdr + [
        ["1.53", "Astro", "Spheric", "Clear", "0.00 To -6.00", "-2.00", "2500"],
        ["1.56", "Astro+", "Aspheric", "Clear", "0.00 To -4.00", "-2.00", "4500"],
    ]
    rows = parser._rows_from_section(hdr, matrix, ParserContext(availability="stock", market="X"))
    assert len(rows) == 2
    assert {r.price for r in rows} == {2500.0, 4500.0}
    assert rows[0].sph_min == -6.0 and rows[0].has_range
    assert all(r.model_hint is None for r in rows)


# -- M. "Hilux 1.5" -> family Hilux + index 1.50 from source text --------
def test_mg_M_type_text_yields_family_and_index(parser):
    assert parser._family_from_type("Hilux 1.5") == "Hilux"
    assert parser._extract_index("Hilux 1.5") == 1.5          # 1.50, not 1.523
    matrix = [list(_H4), ["Hilux 1.5", "Hi Vision Aqua", "1350", "Sph (0.00 To -4.00) Cyl (-2.00) 70"]]
    r = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))[0]
    assert r.model_hint == "Hilux"
    assert r.index_value == 1.5


# -- N. explicit price stays exact --------------------------------------
def test_mg_N_explicit_price_exact(parser):
    matrix = [list(_H4),
              ["Nulux 1.74", "Hi Vision Meiryo", "16300", "Sph (0.00 To -10.00) Cyl (-2.00) 70"]]
    r = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))[0]
    assert r.price == 16300.0


# -- O. unsupported Stock Range grammar -> no fabricated PowerRange ------
def test_mg_O_compound_range_not_fabricated(parser):
    # a genuinely unsupported grammar (Total Sph+Cyl = G3) - NOT G1 - must never
    # be turned into sph/cyl values.
    txt = "Total Sph+Cyl (-8.00) Cyl (-3.00) 70"
    matrix = [list(_H4), ["Nulux 1.74", "Hi Vision Meiryo", "16300", txt]]
    r = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))[0]
    assert r.has_range is False
    assert r.sph_min == 0.0 and r.sph_max == 0.0
    assert r.cyl_min == -10.0 and r.cyl_max == 0.0          # dataclass default, untouched
    assert "unparsed stock range grammar" in r.review_reasons
    assert txt in (r.notes or "")


# -- P. add-on recognition unchanged in merged mode --------------------
def test_mg_P_addon_label_still_skipped(parser):
    matrix = [list(_H4),
              ["Hilux 1.5", "Hi Vision Aqua", "1350", "0.00 to -4.00"],
              ["Blue Cut", "", "50", "0.00 to -2.00"]]
    rows = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))
    assert len(rows) == 1
    assert rows[0].price == 1350.0


# -- L. PIXEL real-catalog geometry behaviour unchanged ----------------
@pytest.mark.skipif(not os.path.exists(_PIXEL), reason="real PIXEL catalog not present")
def test_mg_L_pixel_catalog_unaffected(parser):
    models = parser.parse_pdf(_PIXEL)
    rows = [pr for m in models for pr in m.power_ranges]
    assert len(rows) > 100
    real_fams = {m.name for m in models if m.name != parser.UNRESOLVED_FAMILY}
    assert real_fams and all(len(f) <= 24 for f in real_fams)
    assert any(r.has_range for r in rows)
    assert any(r.design_variant in ("Core", "Advance", "Premium", "Free Form", "High Definition")
               for r in rows)


# -- real HOYA page 4 only: merged reconstruction + subgroup ownership --
@pytest.mark.skipif(not os.path.exists(_HOYA), reason="real HOYA catalog not present")
def test_mg_real_hoya_page4_merged_price_groups(parser):
    import pdfplumber
    with pdfplumber.open(_HOYA) as pdf:
        page = pdf.pages[3]
        subs = parser._reconstruct_merged_price_groups(page)
        cands = parser._extract_page_tables(page)

    assert cands and all(ov.get("_merged") for ov, _, _ in cands)   # page is authoritative
    prices = [m[1][2] for _, _, m in subs]
    assert prices.count("1350") == 1 and prices.count("1450") == 1

    m1350 = next(m for _, _, m in subs if m[1][2] == "1350")
    m1450 = next(m for _, _, m in subs if m[1][2] == "1450")
    assert m1350[1][0] == "Hilux 1.5" and m1350[1][1] == "Hi Vision Aqua"
    assert m1450[1][0] == "Hilux 1.5" and m1450[1][1] == "Hi Vision Aqua"

    r1350 = [r[3] for r in m1350[1:]]
    r1450 = [r[3] for r in m1450[1:]]
    assert r1350 == [
        "Sph (0.00 To -4.00) Cyl (-2.00) 70",
        "Sph (0.00 To +3.00) Cyl (+2.00) 65",
        "Sph (0.00 To +4.00) Cyl (+2.00) 60",
        "Sph (+0.25 To +1.75) Cyl (-2.00) 65",
    ]
    assert r1450 == [
        "Sph (0.00 To -3.00) Cyl (-2.00) 70",
        "Sph (0.00 To +1.00) Cyl (+3.00) 65",
    ]
    assert set(r1350).isdisjoint(set(r1450))

    # downstream: Type -> family Hilux + index 1.50, price exact, no fabricated range
    rows = []
    for ov, hdr, mat in cands:
        rows += parser._rows_from_section(hdr, mat, parser._section_context(ParserContext(), ov))
    hil = [r for r in rows if r.model_hint == "Hilux" and r.price == 1350.0]
    assert hil
    assert all(r.index_value == 1.5 for r in hil)
    # G1 lines parse into real ranges now (OLD-catalog page: same G1 grammar).
    assert all(r.has_range is True for r in hil)
    assert {(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in hil} == {
        (-4.0, 0.0, -2.0, 0.0),
        (0.0, 3.0, 0.0, 2.0),
        (0.0, 4.0, 0.0, 2.0),
        (0.25, 1.75, -2.0, 0.0),
    }
    assert all("unparsed stock range grammar" not in r.review_reasons for r in hil)


# ===========================================================================
# UPDATED HOYA dual price column.  The meaning of two numeric price values in
# one cell CANNOT be read from geometry.  Default => no price, needs_review.
# Only an EXPLICIT, human-confirmed policy string lets the parser take the
# right-hand value as retail (left = wholesale, source-evidence only).
# ===========================================================================
_HOYA_UPD = os.path.join(os.path.expanduser("~"), "Downloads",
                         "Hoya_Price_List_2025_Updated.pdf")
_LWRR = PDFHybridParser.DUAL_PRICE_LEFT_WHOLESALE_RIGHT_RETAIL


@pytest.fixture()
def parser_lwrr():
    return PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)


def _dual(parser, *, retail1="1350", wh1="600", retail2="1450", wh2="650"):
    # two price y-lines; dotted rule at y=40 splits the two PowerRange subgroups.
    return parser._build_price_subgroups(
        list(_H4), 0.0, 100.0,
        [(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        [(15, retail1, wh1, f"{wh1} {retail1}"),
         (60, retail2, wh2, f"{wh2} {retail2}")],
        [(10, "Ra"), (25, "Rb"), (45, "Rc"), (55, "Rd")],
        [], [40],
    )


def _dual_unresolved(parser):
    # what _merged_table_to_subgroups produces with NO policy: retail=None
    return parser._build_price_subgroups(
        list(_H4), 0.0, 100.0,
        [(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        [(15, None, None, "600 1350"), (60, None, None, "650 1450")],
        [(10, "Ra"), (25, "Rb"), (45, "Rc"), (55, "Rd")],
        [], [40],
    )


# -- structural trigger (unchanged) ------------------------------------------
def test_mgu_trigger_updated_5col_grid(parser):
    grid = [["Type", "Coating", "Price", "", "Stock Range"],
            [None, "", "600", "1350", None],
            [None, None, "650", "1450", None],
            [None, "", "1500", "3300", None]]
    assert parser._is_sparse_merged_grid(grid, grid[0]) is True
    old = [["Type", "Coating", "Price", "Stock Range"],
           [None, "", "1350", None], [None, None, "1450", None]]
    assert parser._is_sparse_merged_grid(old, old[0]) is True
    full = [["Index", "Coating", "Price"],
            ["1.5", "Astro", "700"], ["1.56", "Astro+", "900"]]
    assert parser._is_sparse_merged_grid(full, full[0]) is False


# -- A. unlabelled dual price + NO policy -> price None, needs_review --------
def test_mgu_A_no_policy_no_price_needs_review(parser):
    assert parser.dual_price_semantics is None
    subs = _dual_unresolved(parser)
    assert len(subs) == 2
    for ov, _hdr, mat in subs:
        assert "retail_source" not in ov          # nothing selected
        assert "wholesale_source" not in ov       # not labelled either
        assert ov["price_values_source"] in ("600 1350", "650 1450")
        assert ov["review_reason"] == (
            "multiple unlabelled price values require confirmed price semantics")
        assert {r[2] for r in mat[1:]} == {""}     # empty price cell


def test_mgu_A2_no_policy_downstream_row_blocked(parser):
    # through _rows_from_section + the parse_pdf review-reason application
    subs = _dual_unresolved(parser)
    rows = []
    for ov, hdr, mat in subs:
        rr = parser._rows_from_section(hdr, mat, parser._section_context(ParserContext(), ov))
        for r in rr:
            if ov.get("review_reason"):
                r.flag_review(ov["review_reason"])
        rows += rr
    assert rows
    assert all(r.price is None for r in rows)
    assert all(r.review_status == "needs_review" for r in rows)
    assert all("multiple unlabelled price values require confirmed price semantics"
               in r.review_reasons for r in rows)
    # no positional guess leaked anywhere
    assert not any(v in (str(r.price), r.notes or "") for r in rows for v in ("600", "650"))


# -- B/C/D. explicit policy -> right-hand token = retail -------------------
def test_mgu_B_policy_two_source_values_captured(parser_lwrr):
    subs = _dual(parser_lwrr)
    got = {(ov["retail_source"], ov.get("wholesale_source")) for ov, _, _ in subs}
    assert got == {("1350", "600"), ("1450", "650")}


def test_mgu_C_policy_commercial_price_is_retail(parser_lwrr):
    subs = _dual(parser_lwrr)
    s1 = next(m for ov, _, m in subs if ov["retail_source"] == "1350")
    assert {r[2] for r in s1[1:]} == {"1350"}
    assert "600" not in {r[2] for r in s1[1:]}


def test_mgu_D_policy_second_subgroup_retail_1450(parser_lwrr):
    subs = _dual(parser_lwrr)
    s2 = next(m for ov, _, m in subs if ov["retail_source"] == "1450")
    assert {r[2] for r in s2[1:]} == {"1450"}
    assert "650" not in {r[2] for r in s2[1:]}


# -- E. no max()/magnitude: 9999 40 + policy -> retail 40 -----------------
def test_mgu_E_policy_no_magnitude_heuristic(parser_lwrr):
    subs = parser_lwrr._build_price_subgroups(
        list(_H4), 0.0, 100.0,
        [(12, "X 1.5"), (30, "CoatX")],
        [(15, "40", "9999", "9999 40")],     # right token 40 is retail, though smaller
        [(10, "Ra")], [], [],
    )
    assert len(subs) == 1
    ov, _hdr, mat = subs[0]
    assert ov["retail_source"] == "40" and ov["wholesale_source"] == "9999"
    assert {r[2] for r in mat[1:]} == {"40"}


# -- F. same 9999 40 WITHOUT policy -> price None / needs_review ----------
def test_mgu_F_no_policy_9999_40_unresolved(parser):
    subs = parser._build_price_subgroups(
        list(_H4), 0.0, 100.0,
        [(12, "X 1.5"), (30, "CoatX")],
        [(15, None, None, "9999 40")],
        [(10, "Ra")], [], [],
    )
    assert len(subs) == 1
    ov, _hdr, mat = subs[0]
    assert "retail_source" not in ov and "wholesale_source" not in ov
    assert ov["review_reason"] == (
        "multiple unlabelled price values require confirmed price semantics")
    assert {r[2] for r in mat[1:]} == {""}


# -- G. single-price cell parses normally without any policy -------------
def test_mgu_G_single_price_unaffected(parser):
    subs = parser._build_price_subgroups(
        list(_H4), 0.0, 100.0,
        [(12, "Hilux 1.5"), (30, "Hi Vision Aqua")],
        [(15, "1350", None, None)],          # single value = commercial price
        [(10, "Ra"), (25, "Rb")], [], [],
    )
    assert len(subs) == 1
    ov, _hdr, mat = subs[0]
    assert ov["retail_source"] == "1350"
    assert "review_reason" not in ov
    assert {r[2] for r in mat[1:]} == {"1350"}
    # legacy 2-tuple price_toks still accepted
    subs2 = parser._build_price_subgroups(
        list(_H4), 0.0, 100.0, [(12, "A"), (30, "B")], [(15, "700")],
        [(10, "r")], [], [])
    assert subs2[0][0]["retail_source"] == "700"


# -- H. wholesale never written to pr.notes -----------------------------
def test_mgu_H_wholesale_not_in_notes(parser_lwrr):
    subs = _dual(parser_lwrr)
    rows = []
    for ov, hdr, mat in subs:
        rr = parser_lwrr._rows_from_section(
            hdr, mat, parser_lwrr._section_context(ParserContext(), ov))
        for r in rr:
            if ov.get("review_reason"):
                r.flag_review(ov["review_reason"])
        rows += rr
    assert rows
    for r in rows:
        assert "wholesale" not in (r.notes or "").lower()
        assert "600" not in (r.notes or "") and "650" not in (r.notes or "")
        assert not any("wholesale" in x.lower() for x in r.review_reasons)


# -- I. no wholesale value in emitted commercial price rows -------------
def test_mgu_I_no_wholesale_in_prices(parser_lwrr):
    subs = _dual(parser_lwrr)
    prices = {r[2] for _, _, m in subs for r in m[1:]}
    assert prices == {"1350", "1450"}
    assert not ({"600", "650"} & prices)


# -- J. merged geometry / dotted subgroup behaviour unchanged ----------
def test_mgu_J_geometry_and_dotted_split_unchanged(parser_lwrr):
    subs = _dual(parser_lwrr)
    assert len(subs) == 2
    for _ov, _hdr, mat in subs:
        for row in mat[1:]:
            assert row[0] == "Hilux 1.5" and row[1] == "Hi Vision Aqua"
    a = {r[3] for r in subs[0][2][1:]}
    b = {r[3] for r in subs[1][2][1:]}
    assert a == {"Ra", "Rb"} and b == {"Rc", "Rd"} and a.isdisjoint(b)


# -- real UPDATED HOYA page 4: DEFAULT parser -> fully review-blocked ---
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD),
                    reason="real UPDATED HOYA catalog not present")
def test_mgu_real_updated_page4_default_blocked(parser):
    import pdfplumber
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[3]
        subs = parser._reconstruct_merged_price_groups(page)
        cands = parser._extract_page_tables(page)
        rows = []
        for ov, hdr, mat in cands:
            rr = parser._rows_from_section(hdr, mat, parser._section_context(ParserContext(), ov))
            for r in rr:
                if ov.get("review_reason"):
                    r.flag_review(ov["review_reason"])
            rows += rr
    assert len(subs) == 10                                # geometry still reconstructs
    assert all(ov.get("_merged") for ov, _, _ in cands)
    for ov, _h, _m in subs:                               # nothing selected, evidence kept
        assert "retail_source" not in ov and "wholesale_source" not in ov
        assert ov.get("price_values_source")
        assert ov["review_reason"] == (
            "multiple unlabelled price values require confirmed price semantics")
    assert rows and all(r.price is None for r in rows)
    assert all(r.review_status == "needs_review" for r in rows)
    assert not any(("wholesale" in (r.notes or "").lower()) for r in rows)
    assert not any(r.price in (600.0, 650.0, 1350.0, 1450.0) for r in rows)


# -- real UPDATED HOYA page 4: EXPLICIT confirmed policy --------------
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD),
                    reason="real UPDATED HOYA catalog not present")
def test_mgu_real_updated_page4_confirmed_policy(parser_lwrr):
    import pdfplumber
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[3]
        subs = parser_lwrr._reconstruct_merged_price_groups(page)
        cands = parser_lwrr._extract_page_tables(page)
        rows = []
        for ov, hdr, mat in cands:
            rows += parser_lwrr._rows_from_section(
                hdr, mat, parser_lwrr._section_context(ParserContext(), ov))

    assert len(subs) == 10
    groups = {(m[1][0], m[1][1]) for _, _, m in subs}
    assert len(groups) == 7 and ("Hilux 1.5", "Hi Vision Aqua") in groups

    ov1350 = next(ov for ov, _, m in subs if ov.get("retail_source") == "1350")
    m1350 = next(m for ov, _, m in subs if ov.get("retail_source") == "1350")
    ov1450 = next(ov for ov, _, m in subs if ov.get("retail_source") == "1450")
    m1450 = next(m for ov, _, m in subs if ov.get("retail_source") == "1450")

    # C/D + 8/9: wholesale internal, retail emitted
    assert ov1350["wholesale_source"] == "600" and ov1350["retail_source"] == "1350"
    assert ov1450["wholesale_source"] == "650" and ov1450["retail_source"] == "1450"
    assert {r[2] for r in m1350[1:]} == {"1350"}
    assert {r[2] for r in m1450[1:]} == {"1450"}

    assert m1450[1][0] == "Hilux 1.5" and m1450[1][1] == "Hi Vision Aqua"

    r1350 = [r[3] for r in m1350[1:]]
    r1450 = [r[3] for r in m1450[1:]]
    assert r1350 == [
        "Sph (0.00 To -4.00) Cyl (-2.00) 70",
        "Sph (0.00 To +3.00) Cyl (+2.00) 65",
        "Sph (0.00 To +4.00) Cyl (+2.00) 60",
        "Sph (+0.25 To +1.75) Cyl (-2.00) 65",
    ]
    # K + updated-wins: corrected -3.00 preserved under retail 1450
    assert r1450 == [
        "Sph (0.00 To -3.00) Cyl (-3.00) 70",
        "Sph (0.00 To +1.00) Cyl (+3.00) 65",
    ]
    assert "Cyl (-2.00)" not in r1450[0]
    assert set(r1350).isdisjoint(set(r1450))

    emitted = {r.price for r in rows if r.price is not None}
    assert 1350.0 in emitted and 1450.0 in emitted
    assert not any(r.price in (600.0, 650.0, 1500.0, 1550.0, 1250.0, 1300.0, 2000.0) for r in rows)
    assert not any("wholesale" in (r.notes or "").lower() for r in rows)

    hil = [r for r in rows if r.model_hint == "Hilux" and r.price == 1350.0]
    assert hil and all(r.index_value == 1.5 for r in hil)


# -- L. PIXEL real-catalog geometry behaviour unchanged ---------------
@pytest.mark.skipif(not os.path.exists(_PIXEL), reason="real PIXEL catalog not present")
def test_mgu_L_pixel_unaffected():
    for pol in (None, _LWRR):
        p = PDFHybridParser(use_vision=False, dual_price_semantics=pol)
        models_ = p.parse_pdf(_PIXEL)
        rows = [pr for m in models_ for pr in m.power_ranges]
        assert len(rows) > 100
        assert any(r.has_range for r in rows)
        assert {m.name for m in models_ if m.name != p.UNRESOLVED_FAMILY}
        assert not any("wholesale" in (r.notes or "").lower() for r in rows)


# -- old OLD-catalog single-price real page still reconstructs --------
@pytest.mark.skipif(not os.path.exists(_HOYA), reason="real OLD HOYA catalog not present")
def test_mgu_old_hoya_single_price_still_works(parser):
    import pdfplumber
    with pdfplumber.open(_HOYA) as pdf:
        subs = parser._reconstruct_merged_price_groups(pdf.pages[3])
    prices = [ov.get("retail_source") for ov, _, _ in subs]
    assert prices.count("1350") == 1 and prices.count("1450") == 1     # single value -> retail
    assert all("review_reason" not in ov for ov, _, _ in subs)


# ===========================================================================
# HOYA Stock Range grammar G1 only:  "Sph (a To b) Cyl (c) [D]"
#   SPH -> [min(a,b), max(a,b)]
#   CYL -> [c,0] if c<0 ; [0,c] if c>0 ; [0,0] if c==0
#   D   -> diameter mm, kept as source evidence only
# G2 / G3 / G4 remain unparsed and needs_review; nothing is fabricated.
# ===========================================================================
def _g1_row(parser, rng_text, *, coating="Hi Vision Aqua"):
    matrix = [list(_H4), ["Hilux 1.5", coating, "1450", rng_text]]
    return parser._rows_from_section(
        matrix[:1], matrix, ParserContext(availability="stock"))[0]


def test_g1_A_minus_line(parser):
    r = _g1_row(parser, "Sph (0.00 To -3.00) Cyl (-3.00) 70")
    assert r.has_range is True
    assert (r.sph_min, r.sph_max) == (-3.0, 0.0)
    assert (r.cyl_min, r.cyl_max) == (-3.0, 0.0)
    assert "unparsed stock range grammar" not in r.review_reasons
    assert "STOCK without PowerRange" not in r.review_reasons


def test_g1_B_plus_line(parser):
    r = _g1_row(parser, "Sph (0.00 To +3.00) Cyl (+2.00) 65")
    assert (r.sph_min, r.sph_max) == (0.0, 3.0)
    assert (r.cyl_min, r.cyl_max) == (0.0, 2.0)
    assert r.has_range is True


def test_g1_C_mixed_endpoints_minus_cyl(parser):
    r = _g1_row(parser, "Sph (+0.25 To +1.75) Cyl (-2.00) 65")
    assert (r.sph_min, r.sph_max) == (0.25, 1.75)
    assert (r.cyl_min, r.cyl_max) == (-2.0, 0.0)


def test_g1_D_endpoint_order_normalised(parser):
    # descending SPH endpoints must still yield min..max
    r1 = parser._parse_g1_stock_range("Sph (0.00 To -4.00) Cyl (-2.00) 70")
    r2 = parser._parse_g1_stock_range("Sph (-4.00 To 0.00) Cyl (-2.00) 70")
    assert r1["sph"] == (-4.0, 0.0) == r2["sph"]
    assert parser._parse_g1_stock_range("Sph (0.00 To 0.00) Cyl (0.00) 70")["cyl"] == (0.0, 0.0)


def test_g1_E_diameter_kept_as_evidence_only(parser):
    r = _g1_row(parser, "Sph (0.00 To -3.00) Cyl (-3.00) 70")
    assert "diameter_mm=70" in (r.notes or "")
    # diameter is not a SPH/CYL field and there is no schema attr for it
    assert not hasattr(r, "diameter")
    # a line with no trailing D still parses, no diameter note
    r2 = _g1_row(parser, "Sph (0.00 To -10.00) Cyl (-2.00)")
    assert r2.has_range and "diameter_mm" not in (r2.notes or "")


def test_g1_F_multiple_lines_stay_separate_or_ranges(parser):
    matrix = [list(_H4),
              ["Hilux 1.5", "Hi Vision Aqua", "1350", "Sph (0.00 To -4.00) Cyl (-2.00) 70"],
              ["Hilux 1.5", "Hi Vision Aqua", "1350", "Sph (0.00 To +3.00) Cyl (+2.00) 65"],
              ["Hilux 1.5", "Hi Vision Aqua", "1350", "Sph (+0.25 To +1.75) Cyl (-2.00) 65"]]
    rows = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))
    assert len(rows) == 3                       # three independent PowerRange rows
    assert all(r.has_range for r in rows)
    assert all(r.price == 1350.0 for r in rows)   # all attached to the same price
    boxes = {(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in rows}
    assert boxes == {
        (-4.0, 0.0, -2.0, 0.0),
        (0.0, 3.0, 0.0, 2.0),
        (0.25, 1.75, -2.0, 0.0),
    }
    # not merged into one bounding box
    assert (min(r.sph_min for r in rows), max(r.sph_max for r in rows)) == (-4.0, 3.0)
    assert len(boxes) == 3


def test_g1_G_matcher_or_semantics_unchanged(db):
    # Two G1 (minus-cyl) alternatives = two PowerRange rows on ONE current
    # VariantPricing. The matcher's pre-existing OR behaviour (any covering
    # range qualifies) is unchanged by G1 parsing. (Plus-cyl G1 cannot enter
    # PowerRange under the current cyl_max in [-10,0] schema - the next blocker.)
    from decimal import Decimal
    from datetime import datetime as _dt
    from app.lens_matcher import lens_matcher as _m
    co = models.Company(name="G1 Co", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    lm = models.LensModel(company_id=co.id, name="Hilux",
                          category=models.LensCategory.SINGLE_VISION)
    db.add(lm); db.commit(); db.refresh(lm)
    var = models.LensVariant(lens_model_id=lm.id, material=models.MaterialType.CR39,
                             index_value=1.5, price=0.0, design_type=models.DesignType.SPHERICAL,
                             is_aspherical=False)
    db.add(var); db.commit(); db.refresh(var)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    vp = models.VariantPricing(
        variant_id=var.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("1350.00"), currency="EGP", source_catalog_id=cat.id,
        effective_from=_dt.utcnow(), effective_to=None, market_scope="Egypt")
    db.add(vp); db.commit(); db.refresh(vp)
    for sph in ((-4.0, 0.0), (-9.0, -3.0)):
        db.add(models.PowerRange(lens_model_id=lm.id, variant_id=var.id, pricing_id=vp.id,
                                 sph_min=sph[0], sph_max=sph[1], cyl_min=-2.0, cyl_max=0.0))
    db.commit()
    assert db.query(models.PowerRange).filter_by(pricing_id=vp.id).count() == 2

    def presc(s, c):
        p = models.Prescription(od_sph_original=s, os_sph_original=s, od_sph=s, os_sph=s,
            od_cyl_original=c, os_cyl_original=c, od_cyl=c, os_cyl=c,
            od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(p); db.commit(); db.refresh(p); return p

    a = _m.match_lenses(db, presc(-2.0, -1.0), None, True, True)[0]
    b = _m.match_lenses(db, presc(-6.0, -1.0), None, True, True)[0]
    out = _m.match_lenses(db, presc(6.0, 0.0), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in a)     # covered by range 1
    assert any(r.source_pricing_id == vp.id for r in b)     # covered by range 2 (OR)
    assert not any(r.source_pricing_id == vp.id for r in out)


def test_g1_H_g2_now_parses_g1_boundary_intact(parser):
    # G2 is now a supported grammar - but it is NOT G1: _parse_g1_stock_range
    # must still return None for "Sph Only From ..." (G1 output unchanged).
    for txt in ("Sph Only From (0.00 To -4.00) 70",
                "Sph Only From (-3.00 To -10.00) 75"):
        assert parser._parse_g1_stock_range(txt) is None
        r = _g1_row(parser, txt)
        assert r.has_range is True
        assert (r.cyl_min, r.cyl_max) == (0.0, 0.0)
        assert "unparsed stock range grammar" not in r.review_reasons


def test_g1_I_g3_deferred_forms_still_unparsed(parser):
    # G3 slice 1 (two-number total + unsigned cap) parses; the DEFERRED G3
    # forms - single-number total, signed Cyl(c) single total, capless total -
    # stay unparsed. G1 parser never matches any "Total Sph+Cyl" line.
    for txt in ("Total Sph+Cyl (-5.00) Cyl (-2.00) 70",   # single signed total
                "Total Sph+Cyl (+11.00 -10.00)"):          # capless two-number total
        assert parser._parse_g1_stock_range(txt) is None
        r = _g1_row(parser, txt)
        assert r.has_range is False
        assert "unparsed stock range grammar" in r.review_reasons


def test_g1_J_g4_still_unparsed(parser):
    for txt in ("Max Cyl (6)", "Max Cyl (5)"):
        assert parser._parse_g1_stock_range(txt) is None
        r = _g1_row(parser, txt)
        assert r.has_range is False
        assert "unparsed stock range grammar" in r.review_reasons


def test_g1_no_fabrication_from_partial_grammar(parser):
    # a G1-looking prefix that is actually incomplete must NOT parse
    for txt in ("Sph (0.00 To -3.00) 70",                 # no Cyl (...)
                "Sph (0.00 To -3.00) Cyl -3.00 70",       # Cyl not parenthesised
                "Sph (0.00) Cyl (-2.00) 70"):             # no "To" range
        assert parser._parse_g1_stock_range(txt) is None


# ---- real UPDATED HOYA page 4, explicit confirmed dual-price policy -------
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD),
                    reason="real UPDATED HOYA catalog not present")
def test_g1_real_updated_page4(parser_lwrr):
    import pdfplumber
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[3]
        cands = parser_lwrr._extract_page_tables(page)
        rows = []
        for ov, hdr, mat in cands:
            rr = parser_lwrr._rows_from_section(
                hdr, mat, parser_lwrr._section_context(ParserContext(), ov))
            for r in rr:
                if ov.get("review_reason"):
                    r.flag_review(ov["review_reason"])
            rows += rr

    # G1 = has_range with a real signed cylinder interval; G2 = has_range with
    # plano cyl [0,0] (now also parsed).
    g1 = [r for r in rows if r.has_range and (r.cyl_min, r.cyl_max) != (0.0, 0.0)]
    g2 = [r for r in rows if r.has_range and (r.cyl_min, r.cyl_max) == (0.0, 0.0)]
    assert len(g1) == 16                              # G1 lines on page 4
    assert len(g2) == 5                               # G2 "Sph Only From" lines on page 4

    r1350 = [r for r in rows if r.price == 1350.0]
    r1450 = [r for r in rows if r.price == 1450.0]
    assert len(r1350) == 4 and all(r.has_range for r in r1350)
    assert len(r1450) == 2 and all(r.has_range for r in r1450)

    boxes_1350 = {(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in r1350}
    assert boxes_1350 == {
        (-4.0, 0.0, -2.0, 0.0),
        (0.0, 3.0, 0.0, 2.0),
        (0.0, 4.0, 0.0, 2.0),
        (0.25, 1.75, -2.0, 0.0),
    }
    boxes_1450 = {(r.sph_min, r.sph_max, r.cyl_min, r.cyl_max) for r in r1450}
    # K + L: the UPDATED corrected value Cyl (-3.00); old -2.00 must NOT appear
    assert (-3.0, 0.0, -3.0, 0.0) in boxes_1450
    assert (0.0, 1.0, 0.0, 3.0) in boxes_1450
    assert not any(box[2:] == (-2.0, 0.0) and box[:2] == (-3.0, 0.0) for box in boxes_1450)

    # diameter kept as evidence on the parsed rows
    assert any("diameter_mm=70" in (r.notes or "") for r in r1450)

    # G3/G4 lines on the page stay unparsed / needs_review, nothing fabricated
    blocked = [r for r in rows if not r.has_range]
    assert blocked and all(r.review_status == "needs_review" for r in blocked)
    assert not any(
        r.has_range and any(k in (r.notes or "")
                            for k in ("Total Sph+Cyl", "Max Cyl"))
        for r in rows
    )
    assert any("Total Sph+Cyl" in (r.notes or "") for r in blocked)


# ===========================================================================
# G1 signed-cylinder END-TO-END on the authoritative UPDATED HOYA catalog:
# parse -> CatalogExtraction -> bulk-confirm -> PowerRange -> matcher, for both
# a minus-CYL and a plus-CYL G1 row. Retail only; wholesale never in output.
# ===========================================================================
from app.lens_matcher import lens_matcher as _sc_matcher, TranspositionEngine as _SCTE


def _hoya_page4_g1_rows():
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[3]
        rows = []
        for ov, hdr, mat in p._extract_page_tables(page):
            rows += p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov))
    return rows


@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g1sc_R_plus_and_S_minus_bulk_confirm_and_match(db):
    rows = _hoya_page4_g1_rows()
    minus = next(r for r in rows if r.has_range and (r.cyl_min, r.cyl_max) == (-3.0, 0.0)
                 and r.price == 1450.0)                       # the corrected 1450 row
    plus = next(r for r in rows if r.has_range and r.cyl_min == 0.0 and r.cyl_max > 0.0)

    co = models.Company(name="HOYA E2E", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="h.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)

    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    p.extracted_models = [ExtractedLensModel(name="Hilux", category="single_vision",
                                             power_ranges=[minus, plus])]
    p.save_extractions_to_db(cat.id, db)
    from app import crud as _c
    for e in _c.get_extractions_by_catalog(db, cat.id):
        _c.confirm_extraction(db, e.id, "qa")
    # S: corrected minus range survived persistence as cyl [-3, 0]
    exts = _c.get_extractions_by_catalog(db, cat.id)
    assert any((e.cyl_min, e.cyl_max) == (-3.0, 0.0) for e in exts)
    assert not any((e.cyl_min, e.cyl_max) == (-2.0, 0.0) and (e.sph_min, e.sph_max) == (-3.0, 0.0)
                   for e in exts)

    # R: bulk-confirm raises NO ValueError, incl. the plus-CYL row
    _c.confirm_catalog_commercial(db, cat.id, "admin")
    prs = db.query(models.PowerRange).all()
    assert any(pr.cyl_min == 0.0 and pr.cyl_max > 0.0 for pr in prs)      # plus range persisted
    assert any((pr.cyl_min, pr.cyl_max) == (-3.0, 0.0) for pr in prs)     # minus range persisted

    # 8: plus-CYL PowerRange matches an optically equivalent prescription
    plus_pr = next(pr for pr in prs if pr.cyl_min == 0.0 and pr.cyl_max > 0.0)
    # choose a minus-form Rx whose plus form lands inside plus_pr
    lo, hi = plus_pr.sph_min, plus_pr.sph_max
    p_sph = (lo + hi) / 2.0
    p_cyl = min(plus_pr.cyl_max, 1.0)
    m_sph, m_cyl, _m_ax = p_sph + p_cyl, -p_cyl, 0          # minus form (S+C, -C)
    rx = models.Prescription(
        od_sph_original=m_sph, os_sph_original=m_sph, od_sph=m_sph, os_sph=m_sph,
        od_cyl_original=m_cyl, os_cyl_original=m_cyl, od_cyl=m_cyl, os_cyl=m_cyl,
        od_axis=90, os_axis=90, od_add=0.0, os_add=0.0)
    db.add(rx); db.commit(); db.refresh(rx)
    res = _sc_matcher.match_lenses(db, rx, None, True, True)[0]
    plus_vp_id = plus_pr.pricing_id
    hit = [r for r in res if r.source_pricing_id == plus_vp_id]
    assert hit, "plus-CYL catalog range did not match its optically equivalent Rx"

    # T: no wholesale leakage anywhere in the commercial output
    vps = db.query(models.VariantPricing).all()
    assert {str(vp.price_pair) for vp in vps} == {"1450.00", "1350.00"}   # retail only
    for wsale in ("600.00", "650.00", "1500.00", "1550.00"):
        assert not any(str(vp.price_pair) == wsale for vp in vps)
    assert not any("wholesale" in (pr.notes or "").lower() for pr in prs)
    for r in res:
        assert "wholesale" not in (r.reason or "").lower()


@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g1sc_U_g3_g4_still_blocked():
    rows = _hoya_page4_g1_rows()
    blocked = [r for r in rows if not r.has_range]
    assert blocked
    assert all(r.review_status == "needs_review" for r in blocked)
    assert all("unparsed stock range grammar" in r.review_reasons for r in blocked)
    # G3 / G4 unsupported grammars never produced sph/cyl
    assert not any(
        r.has_range and any(k in (r.notes or "")
                            for k in ("Total Sph+Cyl", "Max Cyl"))
        for r in rows
    )
    # a real "Total Sph+Cyl ..." line is still among the blocked rows
    assert any("Total Sph+Cyl" in (r.notes or "") for r in blocked)


# ===========================================================================
# HOYA Stock Range grammar G2 only:  "Sph Only From (a To b) [D]"
#   SPH -> [min(a,b), max(a,b)]     CYL -> [0.00, 0.00]  (spherical-only blank)
#   D   -> diameter mm, source evidence only
# G1 unchanged; G3 / G4 remain unparsed / needs_review; nothing fabricated.
# ===========================================================================
def _g2_row(parser, rng_text, *, coating="Hi Vision Aqua", price="3300"):
    matrix = [list(_H4), ["Hilux 1.5", coating, price, rng_text]]
    return parser._rows_from_section(
        matrix[:1], matrix, ParserContext(availability="stock"))[0]


def test_g2_A_pos_neg_interval_with_diameter(parser):
    r = _g2_row(parser, "Sph Only From (-4.00 To +4.00) 65")
    assert r.has_range is True
    assert (r.sph_min, r.sph_max) == (-4.0, 4.0)
    assert (r.cyl_min, r.cyl_max) == (0.0, 0.0)
    assert "diameter_mm=65" in (r.notes or "")
    assert "unparsed stock range grammar" not in r.review_reasons


def test_g2_B_negative_interval(parser):
    r = _g2_row(parser, "Sph Only From (0.00 To -6.00) 70")
    assert (r.sph_min, r.sph_max) == (-6.0, 0.0)
    assert (r.cyl_min, r.cyl_max) == (0.0, 0.0)
    assert r.has_range is True


def test_g2_C_endpoint_order_normalised(parser):
    for txt in ("Sph Only From (-4.00 To +4.00)", "Sph Only From (+4.00 To -4.00)"):
        g = parser._parse_g2_stock_range(txt)
        assert g["sph"] == (-4.0, 4.0)
    assert parser._parse_g2_stock_range("Sph Only From (-3.00 To -10.00) 75")["sph"] == (-10.0, -3.0)


def test_g2_D_positive_only_interval(parser):
    r = _g2_row(parser, "Sph Only From (+6.25 To +8.00) 65")
    assert (r.sph_min, r.sph_max) == (6.25, 8.0)
    assert (r.cyl_min, r.cyl_max) == (0.0, 0.0)


def test_g2_E_negative_only_interval(parser):
    r = _g2_row(parser, "Sph Only From (-3.00 To -10.00) 75")
    assert (r.sph_min, r.sph_max) == (-10.0, -3.0)
    assert (r.cyl_min, r.cyl_max) == (0.0, 0.0)


def test_g2_F_cyl_is_exactly_plano(parser):
    for txt in ("Sph Only From (-4.00 To +4.00) 65",
                "Sph Only From (0.00 To -6.00) 70",
                "Sph Only From (0.00 To -4.00)"):
        g = parser._parse_g2_stock_range(txt)
        assert g["cyl"] == (0.0, 0.0)


def test_g2_G_multiple_lines_stay_separate_or_ranges(parser):
    matrix = [list(_H4),
              ["Hilux 1.5", "Hi Vision Aqua", "3300", "Sph Only From (0.00 To -4.00) 70"],
              ["Hilux 1.5", "Hi Vision Aqua", "3300", "Sph Only From (0.00 To +4.00) 65"],
              ["Hilux 1.5", "Hi Vision Aqua", "3300", "Sph Only From (+6.25 To +8.00) 65"]]
    rows = parser._rows_from_section(matrix[:1], matrix, ParserContext(availability="stock"))
    assert len(rows) == 3
    assert all(r.has_range for r in rows)
    assert all((r.cyl_min, r.cyl_max) == (0.0, 0.0) for r in rows)
    assert all(r.price == 3300.0 for r in rows)
    boxes = {(r.sph_min, r.sph_max) for r in rows}
    assert boxes == {(-4.0, 0.0), (0.0, 4.0), (6.25, 8.0)}
    # not merged into one bounding box
    assert (min(r.sph_min for r in rows), max(r.sph_max for r in rows)) == (-4.0, 8.0)
    assert len(boxes) == 3


def test_g2_H_g1_unchanged(parser):
    r = _g1_row(parser, "Sph (0.00 To -3.00) Cyl (-3.00) 70")
    assert r.has_range is True
    assert (r.sph_min, r.sph_max) == (-3.0, 0.0)
    assert (r.cyl_min, r.cyl_max) == (-3.0, 0.0)          # signed minus-cyl, not plano
    assert "diameter_mm=70" in (r.notes or "")
    # G2 parser must reject a G1 line
    assert parser._parse_g2_stock_range("Sph (0.00 To -3.00) Cyl (-3.00) 70") is None


def test_g2_I_g3_deferred_forms_still_blocked(parser):
    # G2 parser never matches "Total Sph+Cyl"; the DEFERRED G3 forms stay
    # unparsed (G3 slice 1 two-number+cap forms are covered by test_g3_*).
    for txt in ("Total Sph+Cyl (-5.00) Cyl (-2.00) 70",
                "Total Sph+Cyl (+11.00 -10.00)"):
        assert parser._parse_g2_stock_range(txt) is None
        r = _g2_row(parser, txt)
        assert r.has_range is False
        assert "unparsed stock range grammar" in r.review_reasons


def test_g2_J_g4_still_blocked(parser):
    for txt in ("Max Cyl (6)", "Max Cyl (5)"):
        assert parser._parse_g2_stock_range(txt) is None
        r = _g2_row(parser, txt)
        assert r.has_range is False
        assert "unparsed stock range grammar" in r.review_reasons


def test_g2_K_malformed_does_not_fabricate(parser):
    for txt in ("Sph Only (-4.00 To +4.00)",           # no "From"
                "Sph Only From (-4.00)",               # single bound, no "To b"
                "Sph From (-4.00 To +4.00)",           # not "Sph Only From"
                "Sph Only From -4.00 To +4.00",        # no parentheses
                "Sph Only From (-4.00 To)",            # missing second bound
                "Sph Only From ()"):                   # empty
        assert parser._parse_g2_stock_range(txt) is None
        r = _g2_row(parser, txt)
        assert r.has_range is False
        assert r.sph_min == 0.0 and r.sph_max == 0.0
        assert r.cyl_min == -10.0 and r.cyl_max == 0.0     # dataclass default, untouched
        assert "unparsed stock range grammar" in r.review_reasons


# -- real updated HOYA G2 rows --------------------------------------------
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g2_L_real_updated_hoya_g2_rows():
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    g2 = []
    with pdfplumber.open(_HOYA_UPD) as pdf:
        for pi in range(3, 12):
            page = pdf.pages[pi]
            for ov, hdr, mat in p._extract_page_tables(page):
                for r in p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov)):
                    if r.has_range and (r.cyl_min, r.cyl_max) == (0.0, 0.0):
                        g2.append(r)
    assert len(g2) >= 5
    assert all((r.cyl_min, r.cyl_max) == (0.0, 0.0) for r in g2)
    assert all(r.sph_min <= r.sph_max for r in g2)
    # every parsed G2 row is spherical-only (no fabricated cyl), retail price only
    assert all(r.price is not None and r.price > 0 for r in g2)
    assert not any("wholesale" in (r.notes or "").lower() for r in g2)


@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g2_M_N_O_bulk_confirm_and_matcher(db):
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    with pdfplumber.open(_HOYA_UPD) as pdf:
        rows = []
        for pi in (3,):
            page = pdf.pages[pi]
            for ov, hdr, mat in p._extract_page_tables(page):
                rows += p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov))
    g2 = next(r for r in rows if r.has_range and (r.cyl_min, r.cyl_max) == (0.0, 0.0))

    co = models.Company(name="G2 E2E", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="h.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p.extracted_models = [ExtractedLensModel(name="Hilux", category="single_vision",
                                             power_ranges=[g2])]
    p.save_extractions_to_db(cat.id, db)
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        _crud.confirm_extraction(db, e.id, "qa")
    # M: G2 row survives parse -> extraction -> bulk-confirm -> PowerRange
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    pr = db.query(models.PowerRange).one()
    assert (pr.cyl_min, pr.cyl_max) == (0.0, 0.0)
    vp = db.query(models.VariantPricing).one()
    assert vp.price_pair == g2_price_decimal(g2.price)

    mid = round((pr.sph_min + pr.sph_max) / 2.0, 2)

    def presc(sph, cyl):
        x = models.Prescription(od_sph_original=sph, os_sph_original=sph, od_sph=sph,
            os_sph=sph, od_cyl_original=cyl, os_cyl_original=cyl, od_cyl=cyl, os_cyl=cyl,
            od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(x); db.commit(); db.refresh(x); return x

    # N: plano-cyl Rx matches the G2 PowerRange
    hit = _matcher.match_lenses(db, presc(mid, 0.0), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in hit)
    # O: same SPH with non-zero CYL must NOT match a spherical-only G2 range
    miss = _matcher.match_lenses(db, presc(mid, -1.5), None, True, True)[0]
    assert not any(r.source_pricing_id == vp.id for r in miss)


def g2_price_decimal(v):
    from decimal import Decimal
    return Decimal(str(v)).quantize(Decimal("0.01"))


# ===========================================================================
# G3 Stock Range slice 1:  "Total Sph+Cyl (a b) [Max ]Cyl (n)"  (two-number
# total envelope + UNSIGNED cyl cap). Authoritative:
#   total_power_min <= SPH+CYL <= total_power_max   (minus-cyl convention)
#   AND abs(CYL) <= max_cyl_abs
# sph_*/cyl_* hold only a false-negative-safe coarse prefilter box.
# ===========================================================================
def _g3_rows(parser, *range_lines, type_="Hilux 1.5", coating="Hi Vision Aqua",
            price="6100"):
    matrix = [list(_H4)] + [[type_, coating, price, rl] for rl in range_lines]
    return parser._rows_from_section(matrix[:1], matrix,
                                     ParserContext(availability="stock"))


def _g3_wrapped(parser, total_line, maxcyl_line, *, price="6100",
                type_="Hilux 1.5", coating="Hi Vision Aqua"):
    # two consecutive matrix rows, cap line has blank identity cells (inherited)
    matrix = [list(_H4),
              [type_, coating, price, total_line],
              ["", "", "", maxcyl_line]]
    return parser._rows_from_section(matrix[:1], matrix,
                                    ParserContext(availability="stock"))


# -- A. wrapped parse -> total/max_cyl_abs + coarse box -----------------
def test_g3_A_wrapped_total_and_cap(parser):
    rows = _g3_wrapped(parser, "Total Sph+Cyl (+11.00 -10.00)", "Max Cyl (6)")
    assert len(rows) == 1
    r = rows[0]
    assert r.has_range is True
    assert (r.total_power_min, r.total_power_max) == (-10.0, 11.0)
    assert r.max_cyl_abs == 6.0
    assert (r.sph_min, r.sph_max) == (-10.0, 17.0)      # coarse box: [tmin, tmax+n]
    assert (r.cyl_min, r.cyl_max) == (-6.0, 0.0)        # coarse box: [-n, 0]
    assert "unparsed stock range grammar" not in r.review_reasons


# -- B. inline unsigned cap -------------------------------------------
def test_g3_B_inline_cap(parser):
    r = _g3_rows(parser, "Total Sph+Cyl (+6.00 -8.00) Cyl (2)")[0]
    assert (r.total_power_min, r.total_power_max) == (-8.0, 6.0)
    assert r.max_cyl_abs == 2.0
    assert (r.sph_min, r.sph_max) == (-8.0, 8.0)
    assert (r.cyl_min, r.cyl_max) == (-2.0, 0.0)


# -- C. positive-only interval --------------------------------------
def test_g3_C_positive_only_interval(parser):
    g = parser._parse_g3_stock_range("Total Sph+Cyl (+0.25 +6.00) Cyl (2)")
    assert g["total"] == (0.25, 6.0) and g["max_cyl_abs"] == 2.0


# -- D. wrapped Total + Max Cyl become ONE clause -----------------
def test_g3_D_wrapped_is_one_clause(parser):
    rows = _g3_wrapped(parser, "Total Sph+Cyl (+8.00 -8.00)", "Max Cyl (6)")
    assert len(rows) == 1 and rows[0].total_power_min == -8.0


# -- E. pairing never crosses a price / Type-Coating boundary -----
def test_g3_E_pairing_respects_boundaries(parser):
    # different price on the Max Cyl row -> NOT paired
    m = [list(_H4),
         ["Hilux 1.5", "Hi Vision Aqua", "6100", "Total Sph+Cyl (+11.00 -10.00)"],
         ["Hilux 1.5", "Hi Vision Aqua", "7900", "Max Cyl (6)"]]
    rows = parser._rows_from_section(m[:1], m, ParserContext(availability="stock"))
    assert len(rows) == 2
    assert all(r.has_range is False for r in rows)
    assert all("unparsed stock range grammar" in r.review_reasons for r in rows)
    # different Coating -> NOT paired
    m2 = [list(_H4),
          ["Hilux 1.5", "Hi Vision Aqua", "6100", "Total Sph+Cyl (+11.00 -10.00)"],
          ["Hilux 1.5", "Super Hi Vision", "6100", "Max Cyl (6)"]]
    rows2 = parser._rows_from_section(m2[:1], m2, ParserContext(availability="stock"))
    assert len(rows2) == 2 and all(r.has_range is False for r in rows2)


# -- F. capless Total stays needs_review --------------------------
def test_g3_F_capless_total_blocked(parser):
    r = _g3_rows(parser, "Total Sph+Cyl (+11.00 -10.00)")[0]
    assert r.has_range is False
    assert r.total_power_min is None and r.max_cyl_abs is None
    assert "unparsed stock range grammar" in r.review_reasons


# -- G/H/I. unsupported G3 forms stay needs_review ---------------
def test_g3_G_single_number_total_blocked(parser):
    for txt in ("Total Sph+Cyl (+6.00) Cyl (2.00)", "Total Sph+Cyl (-5.00) Cyl (-2.00) 70"):
        assert parser._parse_g3_stock_range(txt) is None
        r = _g3_rows(parser, txt)[0]
        assert r.has_range is False
        assert "unparsed stock range grammar" in r.review_reasons


def test_g3_H_empty_total_blocked(parser):
    assert parser._parse_g3_stock_range("Total Sph+Cyl ()") is None
    r = _g3_rows(parser, "Total Sph+Cyl ()")[0]
    assert r.has_range is False
    assert "unparsed stock range grammar" in r.review_reasons


def test_g3_I_signed_single_total_blocked(parser):
    r = _g3_rows(parser, "Total Sph+Cyl (-8.00) Cyl (-3.00) 70")[0]
    assert r.has_range is False and r.total_power_min is None
    assert "unparsed stock range grammar" in r.review_reasons


# -- J. total constraint rejects an Rx that passes the loose box ---
def test_g3_J_total_envelope_rejects_box_pass(db):
    from datetime import datetime as _dt
    from decimal import Decimal
    co = models.Company(name="G3J", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    lm = models.LensModel(company_id=co.id, name="Hilux",
                          category=models.LensCategory.SINGLE_VISION)
    db.add(lm); db.commit(); db.refresh(lm)
    v = models.LensVariant(lens_model_id=lm.id, material=models.MaterialType.CR39,
                           index_value=1.5, price=0.0,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False)
    db.add(v); db.commit(); db.refresh(v)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("6100.00"), currency="EGP", source_catalog_id=cat.id,
        effective_from=_dt.utcnow(), effective_to=None, market_scope="Egypt")
    db.add(vp); db.commit(); db.refresh(vp)
    # total in [-10, +11], |cyl| <= 6 ; coarse box sph[-10,17] cyl[-6,0]
    db.add(models.PowerRange(lens_model_id=lm.id, variant_id=v.id, pricing_id=vp.id,
        sph_min=-10.0, sph_max=17.0, cyl_min=-6.0, cyl_max=0.0,
        total_power_min=-10.0, total_power_max=11.0, max_cyl_abs=6.0))
    db.commit()

    def presc(s, c):
        p = models.Prescription(od_sph_original=s, os_sph_original=s, od_sph=s, os_sph=s,
            od_cyl_original=c, os_cyl_original=c, od_cyl=c, os_cyl=c,
            od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(p); db.commit(); db.refresh(p); return p

    # inside envelope -> match
    inside = _matcher.match_lenses(db, presc(-8.0, 0.0), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in inside)
    # SPH -14 / CYL 0 : passes coarse sph box [-10-.., 17]? -14 < -10-0.25 -> box already excludes; use -10/-... pick a box-pass, envelope-fail:
    # SPH -10 / CYL -5 : box sph -10 ok (>= -10-0.25), cyl -5 in [-6,0] -> box PASS ; total = -15 < -10 -> envelope FAIL
    fp = _matcher.match_lenses(db, presc(-10.0, -5.0), None, True, True)[0]
    assert not any(r.source_pricing_id == vp.id for r in fp)


# -- K. max_cyl_abs rejects abs(CYL) above cap --------------------
def test_g3_K_cap_rejects_high_cyl(db):
    from datetime import datetime as _dt
    from decimal import Decimal
    co = models.Company(name="G3K", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    lm = models.LensModel(company_id=co.id, name="Hilux",
                          category=models.LensCategory.SINGLE_VISION)
    db.add(lm); db.commit(); db.refresh(lm)
    v = models.LensVariant(lens_model_id=lm.id, material=models.MaterialType.CR39,
                           index_value=1.5, price=0.0,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False)
    db.add(v); db.commit(); db.refresh(v)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("6100.00"), currency="EGP", source_catalog_id=cat.id,
        effective_from=_dt.utcnow(), effective_to=None, market_scope="Egypt")
    db.add(vp); db.commit(); db.refresh(vp)
    db.add(models.PowerRange(lens_model_id=lm.id, variant_id=v.id, pricing_id=vp.id,
        sph_min=-8.0, sph_max=8.0, cyl_min=-2.0, cyl_max=0.0,
        total_power_min=-8.0, total_power_max=6.0, max_cyl_abs=2.0))
    db.commit()

    def presc(s, c):
        p = models.Prescription(od_sph_original=s, os_sph_original=s, od_sph=s, os_sph=s,
            od_cyl_original=c, os_cyl_original=c, od_cyl=c, os_cyl=c,
            od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(p); db.commit(); db.refresh(p); return p

    ok = _matcher.match_lenses(db, presc(-2.0, -1.5), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in ok)
    # |cyl| = 3 > cap 2 (and box cyl_min -2 also excludes, but cap is the point)
    bad = _matcher.match_lenses(db, presc(-1.0, -3.0), None, True, True)[0]
    assert not any(r.source_pricing_id == vp.id for r in bad)


# -- L. boundary values are inclusive ---------------------------
def test_g3_L_inclusive_boundaries():
    from app.lens_matcher import LensMatcherFinal
    m = LensMatcherFinal()
    pr = type("PR", (), dict(sph_min=-10.0, sph_max=17.0, cyl_min=-6.0, cyl_max=0.0,
                             add_min=None, add_max=None, max_cyl_for_high_sph=None,
                             sph_threshold=None, total_power_min=-10.0,
                             total_power_max=11.0, max_cyl_abs=6.0))()
    assert m._check_form_against_range(pr, (-6.0, -4.0, 0, 0.0)) == []      # total exactly -10
    assert m._check_form_against_range(pr, (11.0, 0.0, 0, 0.0)) == []       # total exactly +11
    assert m._check_form_against_range(pr, (0.0, -6.0, 0, 0.0)) == []       # |cyl| exactly 6


# -- M. G3 uses minus form only --------------------------------
def test_g3_M_minus_convention():
    from app.lens_matcher import LensMatcherFinal
    m = LensMatcherFinal()
    pr = type("PR", (), dict(cyl_min=-6.0, cyl_max=0.0, total_power_min=-10.0,
                             total_power_max=11.0, max_cyl_abs=6.0))()
    assert m._range_convention(pr) == "minus"           # never "both", never "plus"


# -- N. same Rx entered plus vs minus -> identical G3 result --
def test_g3_N_entry_notation_independent(db):
    from datetime import datetime as _dt
    from decimal import Decimal
    from app.lens_matcher import TranspositionEngine as _TE
    co = models.Company(name="G3N", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    lm = models.LensModel(company_id=co.id, name="Hilux",
                          category=models.LensCategory.SINGLE_VISION)
    db.add(lm); db.commit(); db.refresh(lm)
    v = models.LensVariant(lens_model_id=lm.id, material=models.MaterialType.CR39,
                           index_value=1.5, price=0.0,
                           design_type=models.DesignType.SPHERICAL, is_aspherical=False)
    db.add(v); db.commit(); db.refresh(v)
    cat = models.Catalog(company_id=co.id, filename="c.pdf", file_path="/x",
                         status=models.CatalogStatus.CONFIRMED)
    db.add(cat); db.commit(); db.refresh(cat)
    vp = models.VariantPricing(variant_id=v.id, availability=models.PricingAvailability.STOCK,
        price_pair=Decimal("6100.00"), currency="EGP", source_catalog_id=cat.id,
        effective_from=_dt.utcnow(), effective_to=None, market_scope="Egypt")
    db.add(vp); db.commit(); db.refresh(vp)
    db.add(models.PowerRange(lens_model_id=lm.id, variant_id=v.id, pricing_id=vp.id,
        sph_min=-10.0, sph_max=17.0, cyl_min=-6.0, cyl_max=0.0,
        total_power_min=-10.0, total_power_max=11.0, max_cyl_abs=6.0))
    db.commit()

    def stored(entered):
        s, c, a = entered
        t = _TE.transpose(s, c, a)
        p = models.Prescription(od_sph_original=s, os_sph_original=s, od_sph=t[0], os_sph=t[0],
            od_cyl_original=c, os_cyl_original=c, od_cyl=t[1], os_cyl=t[1],
            od_axis=t[2], os_axis=t[2], od_add=0.0, os_add=0.0)
        db.add(p); db.commit(); db.refresh(p); return p

    minus_entry = stored((-6.0, -2.0, 90))          # total -8
    plus_entry = stored((-8.0, 2.0, 180))           # transposes to (-6, -2, 90) -> same
    assert (minus_entry.od_sph, minus_entry.od_cyl) == (plus_entry.od_sph, plus_entry.od_cyl)
    a = {r.source_pricing_id for r in _matcher.match_lenses(db, minus_entry, None, True, True)[0]}
    b = {r.source_pricing_id for r in _matcher.match_lenses(db, plus_entry, None, True, True)[0]}
    assert vp.id in a and a == b


# -- O. two G3 clauses under one price stay OR alternatives ---
def test_g3_O_two_clauses_or(parser):
    rows = _g3_rows(parser,
                    "Total Sph+Cyl (+6.00 -6.00) Cyl (2)",
                    "Total Sph+Cyl (+6.00 -8.00) Cyl (3)")
    assert len(rows) == 2
    assert {(r.total_power_min, r.total_power_max, r.max_cyl_abs) for r in rows} == {
        (-6.0, 6.0, 2.0), (-8.0, 6.0, 3.0)}
    assert all(r.price == 6100.0 for r in rows)


# -- P. distinct G3 power_scope prevents identity collision ---
def test_g3_P_distinct_power_scope():
    from app.crud import build_power_scope
    s1 = build_power_scope(-6.0, 8.0, -2.0, 0.0, None, None, -6.0, 6.0, 2.0)
    s2 = build_power_scope(-6.0, 8.0, -2.0, 0.0, None, None, -8.0, 6.0, 3.0)
    assert s1 != s2
    assert "total:" in s1 and "maxcyl:" in s1
    # a non-G3 call is unchanged (no total/maxcyl segment)
    s0 = build_power_scope(-4.0, 0.0, -2.0, 0.0)
    assert "total:" not in s0 and "maxcyl:" not in s0


# -- Q. parse -> CatalogExtraction -> bulk-confirm -> PowerRange preserves fields
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g3_Q_e2e_preserves_fields(db):
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    g3 = None
    with pdfplumber.open(_HOYA_UPD) as pdf:
        for pi in (8, 9, 11):                       # pages 9, 10, 12
            page = pdf.pages[pi]
            for ov, hdr, mat in p._extract_page_tables(page):
                for r in p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov)):
                    if r.has_range and r.total_power_min is not None:
                        g3 = r
            if g3:
                break
    assert g3 is not None
    co = models.Company(name="G3Q", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="h.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p.extracted_models = [ExtractedLensModel(name=g3.model_hint or "Hilux",
                                             category="single_vision", power_ranges=[g3])]
    p.save_extractions_to_db(cat.id, db)
    exts = _crud.get_extractions_by_catalog(db, cat.id)
    assert any(e.extracted_total_power_min is not None for e in exts)
    for e in exts:
        _crud.confirm_extraction(db, e.id, "qa")
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    pr = db.query(models.PowerRange).one()
    assert pr.total_power_min == g3.total_power_min
    assert pr.total_power_max == g3.total_power_max
    assert pr.max_cyl_abs == g3.max_cyl_abs
    vp = db.query(models.VariantPricing).one()
    assert "total:" in (vp.power_scope or "")


# -- R. real updated-HOYA G3 E2E reaches matcher ---------------
@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g3_R_real_e2e_matcher(db):
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    g3 = None
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[8]                          # page 9, Special Order XR
        for ov, hdr, mat in p._extract_page_tables(page):
            for r in p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov)):
                if r.has_range and r.total_power_min is not None and g3 is None:
                    g3 = r
    assert g3 is not None
    co = models.Company(name="G3R", is_active=True, is_deleted=False)
    db.add(co); db.commit(); db.refresh(co)
    cat = models.Catalog(company_id=co.id, filename="h.pdf", file_path="/x",
                         status=models.CatalogStatus.DRAFT)
    db.add(cat); db.commit(); db.refresh(cat)
    p.extracted_models = [ExtractedLensModel(name=g3.model_hint or "Hilux",
                                             category="single_vision", power_ranges=[g3])]
    p.save_extractions_to_db(cat.id, db)
    for e in _crud.get_extractions_by_catalog(db, cat.id):
        _crud.confirm_extraction(db, e.id, "qa")
    _crud.confirm_catalog_commercial(db, cat.id, "admin")
    vp = db.query(models.VariantPricing).one()
    tmid = round((g3.total_power_min + g3.total_power_max) / 2.0, 2)

    def presc(s, c):
        x = models.Prescription(od_sph_original=s, os_sph_original=s, od_sph=s, os_sph=s,
            od_cyl_original=c, os_cyl_original=c, od_cyl=c, os_cyl=c,
            od_axis=0, os_axis=0, od_add=0.0, os_add=0.0)
        db.add(x); db.commit(); db.refresh(x); return x

    hit = _matcher.match_lenses(db, presc(tmid, 0.0), None, True, True)[0]
    assert any(r.source_pricing_id == vp.id for r in hit)
    # far outside the envelope -> excluded
    miss = _matcher.match_lenses(db, presc(g3.total_power_min - 15.0, 0.0), None, True, True)[0]
    assert not any(r.source_pricing_id == vp.id for r in miss)
    # S: retail only, no wholesale value as a price
    assert vp.price_pair == g3_price_dec(g3.price)


def g3_price_dec(v):
    from decimal import Decimal
    return Decimal(str(v)).quantize(Decimal("0.01"))


@pytest.mark.skipif(not os.path.exists(_HOYA_UPD), reason="real UPDATED HOYA catalog not present")
def test_g3_S_no_wholesale_leak(db):
    import pdfplumber
    p = PDFHybridParser(use_vision=False, dual_price_semantics=_LWRR)
    with pdfplumber.open(_HOYA_UPD) as pdf:
        page = pdf.pages[8]
        rows = []
        for ov, hdr, mat in p._extract_page_tables(page):
            rows += p._rows_from_section(hdr, mat, p._section_context(ParserContext(), ov))
    g3 = [r for r in rows if r.has_range and r.total_power_min is not None]
    assert g3
    # left-column wholesale values on page 9 are 2900/3750/3950/4650/... - none
    # of them may be a parsed G3 row's commercial price
    assert not any(r.price in (2900.0, 3750.0, 3950.0, 4650.0, 6200.0) for r in g3)
    assert not any("wholesale" in (r.notes or "").lower() for r in g3)
