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
