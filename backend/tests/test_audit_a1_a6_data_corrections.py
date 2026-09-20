"""Regression guard for Catalog Truth Audit (2026-09-18) Section A items
A1-A6: six catalog-proven, zero-ambiguity value corrections on specific,
already-imported rows in the certified runtime database
(backend/release_runtime.db - see app/database.py). A7 (the impact-resistance
rule) was a code fix, already covered by
test_seller_priority_v141.py/test_seller_workflow.py.

Unlike every other test in this suite, this file intentionally reads the
live release_runtime.db rather than a synthetic fixture: these are one-time,
row-id-specific data corrections against real imported catalog rows (see
audit.md Section A), not a code/logic rule a synthetic catalog can exercise.
Read-only - never opens the db for writing; the correction itself is applied
out-of-band (see the audit) with its own SQLite online backup taken first.
"""
import os
import sqlite3

import pytest

from app.database import engine

_DB_PATH = os.path.abspath(engine.url.database) if engine.url.database else None
pytestmark = pytest.mark.skipif(
    not _DB_PATH or not os.path.exists(_DB_PATH),
    reason="live release_runtime.db not present")


def _rows(query, params=()):
    con = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
    try:
        return con.execute(query, params).fetchall()
    finally:
        con.close()


def test_a1_zeiss_1_53_variants_are_trivex():
    # audit.md A1 / Section G item 4: p.8 (3x) prints index 1.53 as
    # "1.53 (Trivex)" with Abbe/Density constants distinct from CR39 - the
    # only ZEISS index with a catalog-proven material correction.
    #
    # Count updated 7 -> 13 (Special Lenses architecture, ZEISS Office
    # Lenses ingestion, owner-confirmed 2026-09-21): the same A1 rule applies
    # unchanged, automatically, via the existing _TRIVEX_1_53_COMPANIES/
    # corrected_identity() correction (no new material code) - it now also
    # covers the 6 new ZEISS "Office" variants at index 1.53 (Clear + Blue
    # Guard treatment bands, one variant per Individual/Superb/Plus tier =
    # 2 bands x 3 tiers = 6), on top of the original 7. See
    # app/zeiss_office_evidence.py for the full ingestion evidence.
    rows = _rows("""select v.id, v.material from lens_variants v
                    join lens_models m on m.id = v.lens_model_id
                    where m.company_id = 2 and v.index_value = 1.53""")
    assert len(rows) == 13
    assert all(material == "TRIVEX" for _id, material in rows)


def test_a2_pixel_1_53_variants_are_trivex():
    # audit.md A2: p.9 headlines "Pixel Trivex 1.53 - High Impact Resistant
    # Lens" explicitly.
    ids = (192, 206, 207, 208, 209, 238, 239, 240, 241)
    rows = _rows(
        f"select id, material from lens_variants where id in ({','.join('?' * len(ids))})", ids)
    assert len(rows) == len(ids)
    assert all(material == "TRIVEX" for _id, material in rows)


def test_a3_hoya_mineral_variants_are_glass():
    # audit.md A3: p.28/p.39 prove HOYA's "Mineral" family is a distinct
    # glass line; models.py already reserves MaterialType.GLASS for exactly
    # this case (SCOPE precedent).
    rows = _rows("select id, material from lens_variants where id between 100 and 106")
    assert len(rows) == 7
    assert all(material == "GLASS" for _id, material in rows)


def test_a4_maxxee_pricing_is_out_of_egypt():
    # audit.md A4: p.2 explicitly captions these rows "Stock Out Of Egypt
    # (5-7 Days)".
    rows = _rows("select id, market_scope from variant_pricing where id in (656, 657)")
    assert len(rows) == 2
    assert all(scope == "Out Of Egypt" for _id, scope in rows)


def test_a5_pixel_astro_coating_uses_its_own_proven_rate():
    # audit.md A5 / Section G item 5 (price part only - see PR notes for the
    # row-count ambiguity left untouched): "Astro" (coating_id=17, variant
    # 187) was priced at the "Astro+B" rate (1300/1400); catalog p.13 proves
    # Astro's own rate is 900/1000. Existing power-range-differentiated rows
    # are left in place; only the wrong price values are corrected.
    rows = _rows("""select id, price_pair from variant_pricing
                    where variant_id = 187 and coating_id = 17""")
    assert len(rows) == 3
    assert {price for _id, price in rows} == {900, 1000}


def test_a6_pixel_variants_are_aspherical():
    # audit.md A6: p.13 proves these 6 rows are Aspheric (only 1.5 and
    # Opal-1.56 are genuinely Spherical for Pixel).
    ids = (187, 188, 189, 193, 194, 195)
    rows = _rows(
        f"select id, design_type, is_aspherical from lens_variants where id in ({','.join('?' * len(ids))})", ids)
    assert len(rows) == len(ids)
    assert all(design_type == "ASPHERICAL" and is_aspherical for _id, design_type, is_aspherical in rows)
