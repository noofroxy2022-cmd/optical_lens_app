"""
PDF Hybrid Parser - مستخرج هجين

يدمج:
1. pdfplumber (للجداول المنظمة)
2. Google Vision API (للجداول الملونة/المركبة)
3. شاشة Preview & Confirm

الأنماط المدعومة:
- جداول بسيطة: SPH | CYL | ADD
- جداول Matrix: SPH × CYL
- جداول ملونة: Stock (أخضر) vs RX (أحمر)
- نطاقات قوة معقدة مع قيود
"""
import re
import os
import json
import pdfplumber
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

try:  # optional - only needed for colour-based Stock/RX detection
    from google.cloud import vision
except Exception:  # pragma: no cover - environment without the SDK
    vision = None
try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None


# ===========================================================================
# Generic commercial vocabulary. NO manufacturer names, page numbers or prices.
# Terms are only APPLIED when the catalog STRUCTURE (column header / heading)
# identifies the concept - a raw token never changes meaning on its own.
# ===========================================================================
DESIGN_VARIANT_TERMS = {
    "free form": "Free Form", "freeform": "Free Form", "free-form": "Free Form",
    "high definition": "High Definition", "hd": "High Definition",
    "core": "Core", "advance": "Advance", "advanced": "Advance",
    "premium": "Premium",
    "d type": "D Type", "d-type": "D Type", "dtype": "D Type",
    "kt type": "KT Type", "kt-type": "KT Type", "kttype": "KT Type",
}

# optical geometry -> design_type ONLY (never design_variant)
OPTICAL_GEOMETRY_TERMS = {
    "spherical": "spherical", "sphere": "spherical",
    "aspheric": "aspherical", "aspherical": "aspherical", "asph": "aspherical", "asp": "aspherical",
    "double aspheric": "double_aspherical", "double aspherical": "double_aspherical",
    "bi-aspheric": "double_aspherical", "bi aspheric": "double_aspherical",
    "atoric": "aspherical",
}

# colour / optical-technology -> color_variant (roots; suffixes like /G/B kept verbatim)
COLOR_VARIANT_ROOTS = {
    "clear": "Clear", "white": "Clear",
    "transmatic": "Transmatic", "transition": "Transition", "transitions": "Transition",
    "photochromic": "Transition", "photo": "Transition",
    "polz": "Polz", "polarized": "Polz", "polarised": "Polz", "polarizing": "Polz",
    "dwear": "DWEAR",
    "g15": "G15", "brown": "Brown", "grey": "Grey", "gray": "Grey", "green": "Green",
}

# add-on / treatment lines -> NOT a base lens, NOT a base colour, NOT a base price row
ADDON_TREATMENT_TERMS = {
    "hi power", "high power", "hi-power",
    "tinting", "tint", "solid tint", "gradient tint",
    "blue cut", "blue-cut", "bluecut", "blue block", "blue-block", "blue light",
    "mirror", "mirror coat", "flash mirror", "revo",
    "add on", "add-on", "surcharge", "extra charge", "upgrade fee",
}

# coating tokens - only meaningful inside a coating/treatment COLUMN or heading
COATING_TERMS = {
    "hmc", "shmc", "hc", "mc", "ar", "arc", "anti reflective", "anti-reflective",
    "multi coat", "multicoat", "green coat", "blue coat", "green coating", "blue coating",
    "super hydrophobic", "hydrophobic", "emi", "uv coat", "uv coating", "hvll", "hvp",
}
COATING_NONE_MARKERS = {
    "", "-", "--", "–", "—", "none", "no coat", "no coating", "uncoated",
    "n/a", "na", "nil", "blank",
}

AVAILABILITY_STOCK_TERMS = {
    "stock", "in stock", "ready", "ready made", "ready-made", "finished", "finish",
    "off the shelf", "off-the-shelf", "available",
}
AVAILABILITY_RX_TERMS = {
    "rx", "prescription", "made to order", "made-to-order", "custom", "customised",
    "customized", "surfacing", "lab", "semi finished", "semi-finished", "sf",
}


_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def _clean(text) -> str:
    s = str(text or "")
    for k, v in _LIGATURES.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()


def _dedouble(text) -> str:
    """Collapse a fully character-doubled token ('AAssttrroo' -> 'Astro',
    'CClleeaarr' -> 'Clear') produced by an overprinted PDF text layer. Only
    applied when EVERY character comes in an identical consecutive pair, so
    legitimate words and numbers are never altered."""
    s = _clean(text)
    if len(s) >= 4 and len(s) % 2 == 0 and re.fullmatch(r"(?:(.)\1)+", s):
        return s[::2]
    # token made of doubled letters plus a shared suffix like '/G/B'
    m = re.match(r"^((?:(.)\2)+)(/[A-Za-z0-9/]+)$", s)
    if m:
        return m.group(1)[::2] + m.group(3)
    return s


def _is_pure_number(text) -> bool:
    s = _clean(text).replace(",", "")
    return bool(re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", s))


@dataclass
class ParserContext:
    """Relational context accumulated from portfolio / heading pages and carried
    forward into later pricing tables. Everything here is derived from catalog
    STRUCTURE, never hardcoded."""
    index: Optional[float] = None
    availability: str = "stock"
    availability_explicit: bool = False
    market: Optional[str] = None
    category: str = "single_vision"
    design_variant: Optional[str] = None
    color_variant: Optional[str] = None
    family_candidates: List[str] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExtractedPowerRange:
    sph_min: float
    sph_max: float
    cyl_min: float = -10.0
    cyl_max: float = 0.0
    add_min: Optional[float] = None
    add_max: Optional[float] = None
    index_value: Optional[float] = None
    material: Optional[str] = None
    availability: str = "stock"
    price: Optional[float] = None
    design_type: str = "spherical"          # optical geometry ONLY
    is_aspherical: bool = False
    # ----- Phase 4 commercial identity -----
    design_variant: Optional[str] = None    # Free Form / High Definition / Core / ...
    color_variant: Optional[str] = None     # Clear / Transmatic/G/B / Polz/G/B / DWEAR ...
    market_scope: Optional[str] = None      # generic: Egypt / Out Of Egypt / ...
    coating: Optional[str] = None
    coating_status: str = "not_found"       # resolved / explicit_none / not_found
    coating_confidence: Optional[float] = None
    has_range: bool = False                 # a real SPH/CYL range was parsed
    is_addon: bool = False
    review_status: str = "pending"          # pending / needs_review
    review_reasons: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_dict(self):
        return asdict(self)

    def flag_review(self, reason: str):
        self.review_status = "needs_review"
        if reason not in self.review_reasons:
            self.review_reasons.append(reason)


@dataclass
class ExtractedLensModel:
    name: str
    name_ar: Optional[str] = None
    lens_code: Optional[str] = None
    category: str = "single_vision"
    description: Optional[str] = None
    features: List[str] = None
    variants: List[Dict[str, Any]] = None
    power_ranges: List[ExtractedPowerRange] = None

    def __post_init__(self):
        if self.features is None:
            self.features = []
        if self.variants is None:
            self.variants = []
        if self.power_ranges is None:
            self.power_ranges = []

    def to_dict(self):
        return {
            "name": self.name,
            "name_ar": self.name_ar,
            "lens_code": self.lens_code,
            "category": self.category,
            "description": self.description,
            "features": self.features,
            "variants": self.variants,
            "power_ranges": [pr.to_dict() for pr in self.power_ranges]
        }


class PDFHybridParser:
    """
    محلل هجين لكتالوجات PDF

    يستخدم pdfplumber للجداول البسيطة
    و Google Vision للجداول المعقدة/الملونة
    """

    # أنماط regex
    INDEX_PATTERNS = [
        re.compile(r"1\.50|1\.56|1\.60|1\.61|1\.67|1\.74", re.IGNORECASE),
        re.compile(r"Index[\s:]*(1\.\d{2})", re.IGNORECASE),
        re.compile(r"(1\.\d{2})[\s]*Index", re.IGNORECASE),
        re.compile(r"Index[\s]+(1\.\d{2})", re.IGNORECASE),
    ]

    SPH_PATTERNS = [
        re.compile(r"SPH[\s:]*([+-]?\d+\.?\d*)[\s]*to[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*≤?[\s]*SPH[\s]*≤?[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*-[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
        re.compile(r"([+-]?\d+\.?\d*)[\s]*~[\s]*([+-]?\d+\.?\d*)", re.IGNORECASE),
    ]

    STOCK_COLORS = [(0, 150, 0), (50, 200, 50), (100, 255, 100)]  # أخضر
    RX_COLORS = [(200, 50, 50), (255, 100, 100), (255, 150, 150)]  # أحمر

    def __init__(self, use_vision: bool = True):
        self.use_vision = use_vision
        self.client = None
        if use_vision and vision is not None:
            try:
                self.client = vision.ImageAnnotatorClient()
            except Exception as e:
                print(f"Warning: Could not initialize Vision API: {e}")

        self.extracted_models: List[ExtractedLensModel] = []
        self.errors: List[str] = []

    def parse_pdf(self, pdf_path: str, company_name: str = "") -> List[ExtractedLensModel]:
        """تحليل PDF كامل"""
        self.extracted_models = []
        self.errors = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                current_model: Optional[ExtractedLensModel] = None
                context = ParserContext()

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""

                    # portfolio / heading text feeds the relational context
                    self._update_context_from_text(context, text)
                    self._ingest_relation_page(context, page, text)

                    model_name = self._extract_model_name(text)
                    if model_name:
                        if current_model:
                            self.extracted_models.append(current_model)
                        current_model = ExtractedLensModel(name=model_name)

                    idx = self._extract_index(text)
                    if idx:
                        context.index = idx

                    if self.client and not context.availability_explicit:
                        avail = self._detect_availability_by_color(page)
                        if avail in ("stock", "rx"):
                            context.availability = avail

                    # ---- multi-strategy table discovery ----
                    for overrides, header, matrix in self._extract_page_tables(page):
                        sect = self._section_context(context, overrides)
                        rows = self._rows_from_section(header, matrix, sect)
                        if not rows:
                            continue
                        # family is resolved PER ROW from relationship evidence
                        # (availability/category/market/commercial terms) - never
                        # from the pricing-section heading, never from price.
                        buckets: Dict[str, list] = {}
                        for r in rows:
                            fam = self._resolve_family(
                                sect,
                                {t for t in (r.coating, r.color_variant, r.design_variant) if t},
                            )
                            if fam is None:
                                fam = self.UNRESOLVED_FAMILY
                                r.flag_review("ambiguous/unresolved product family")
                            buckets.setdefault(fam, []).append(r)
                        for fam, brs in buckets.items():
                            m = ExtractedLensModel(name=fam, category=sect.category)
                            m.power_ranges.extend(brs)
                            self.extracted_models.append(m)
                    current_model = None

                if current_model and current_model not in self.extracted_models:
                    self.extracted_models.append(current_model)

                self._consolidate_variants()

        except Exception as e:
            self.errors.append(f"Error: {str(e)}")

        return self.extracted_models

    # ------------------------------------------------------------------ context
    def _update_context_from_text(self, context: "ParserContext", text: str):
        """Harvest market / availability / category / design / family relations
        from a page's heading text. Structure-driven, no hardcoded manufacturer."""
        low = (text or "").lower()

        market = self._harvest_market(text)
        if market:
            context.market = market

        # explicit availability heading (e.g. "RX", "Stock", "Made to Order")
        if any(t in low for t in AVAILABILITY_RX_TERMS):
            context.availability, context.availability_explicit = "rx", True
        elif any(t in low for t in AVAILABILITY_STOCK_TERMS):
            context.availability, context.availability_explicit = "stock", True

        # relational rule: a "Finished / Ready" + "Single Vision" heading means
        # STOCK even if the word "Stock" never appears
        if "single vision" in low or re.search(r"\bsv\b", low):
            context.category = "single_vision"
            if any(w in low for w in ("finished", "finish", "ready", "off the shelf")):
                context.availability, context.availability_explicit = "stock", True
        elif "progressive" in low:
            context.category = "progressive"
        elif "bifocal" in low:
            context.category = "bifocal"

        # design / colour terms mentioned in a portfolio/overview heading
        for term, canon in DESIGN_VARIANT_TERMS.items():
            if term in low:
                context.design_variant = canon
                break

    # words that can never be a product family on their own
    FAMILY_STOPWORDS = {
        "design", "designs", "technology", "coating", "coatings", "surface",
        "portfolio", "overview", "range", "contents", "index", "coating",
        "lens", "lenses", "single", "vision", "progressive", "bifocal", "focal",
        "price", "pricing", "color", "colour", "sph", "cyl", "add", "power",
        "stock", "finished", "rx", "prescription", "material", "clear", "egypt",
        "outside", "out of egypt", "retail", "list", "treatments", "treatment",
        "aspheric", "spheric", "aspherical", "spherical", "core", "advance",
        "premium", "free form", "high definition", "d type", "kt type",
        "product", "products", "envisioning life",
    }

    def _looks_like_family(self, s: str) -> bool:
        s = _clean(s)
        if not (3 <= len(s) <= 24):
            return False
        low = s.lower().strip(" .,:-")
        if low in self.FAMILY_STOPWORDS:
            return False
        if all(w in self.FAMILY_STOPWORDS for w in low.split()):
            return False
        if _is_pure_number(s):
            return False
        # colour / geometry / design tokens are never a family; likewise a known
        # coating word (but NOT the generic "anything in a Coating column" rule)
        if (self._classify_color(s) or self._classify_geometry(s)
                or self._classify_design(s)
                or any(re.search(rf"\b{re.escape(t)}\b", low) for t in COATING_TERMS)):
            return False
        # short ALL-CAPS acronyms (EMI, HD, FF, DAS, UV) are not families
        if s.isupper() and len(s) <= 4:
            return False
        common = {"comparison", "clarity", "hazardous", "performance", "mission",
                  "philosophy", "standard", "designs", "technology", "protection",
                  "impact", "resistant", "polarized", "lenses", "treatments"}
        if low in common or any(w in common for w in low.split()):
            return False
        return bool(re.fullmatch(r"[A-Z][A-Za-z0-9][A-Za-z0-9 +\-/]{1,22}", s))

    _REL_STOPWORDS = {
        "stock", "rx", "lens", "lenses", "single", "vision", "progressive",
        "bifocal", "focal", "bi", "prescription", "outside", "egypt", "of",
        "out", "product", "portfolio", "overview", "range", "designs",
    }

    def _ingest_relation_page(self, context: "ParserContext", page, text: str):
        """Geometry-aware read of a portfolio / overview relation table.

        The family label lives in its own vertical column, physically OFFSET from
        the availability / category / technology / market cells of the same visual
        relation row. We locate that family column by x-position and bind each
        relation row to the family label nearest in y. No hardcoded families,
        pages or prices."""
        low = (text or "").lower()
        if not any(w in low for w in ("portfolio", "overview", "product family", "product range")):
            return
        try:
            words = self._dedup_overprint_words(page)
        except Exception:
            words = []
        if not words:
            return

        def cx(w):
            return (w["x0"] + w["x1"]) / 2

        # candidate family tokens anywhere on the page -> their column band
        fam_words = [w for w in words if self._looks_like_family(w["text"])]
        if not fam_words:
            return
        fam_xs = sorted(cx(w) for w in fam_words)
        # densest ~40px x-window = the family column centre
        best_c, best_n = fam_xs[0], 0
        for c in fam_xs:
            n = sum(1 for x in fam_xs if abs(x - c) <= 24)
            if n > best_n:
                best_c, best_n = c, n
        fam_col = [w for w in fam_words if abs(cx(w) - best_c) <= 26]
        if len({_clean(w["text"]) for w in fam_col}) < 1:
            return

        # relation anchor rows: a line with an availability keyword at low x
        lines = self._cluster_lines(words)
        anchors = []
        for ws in lines:
            left = [w for w in ws if cx(w) < 170]
            lt = " ".join(w["text"] for w in left).lower()
            if ("stock" in lt or "rx" in lt or "prescription" in lt) and "lens" in " ".join(w["text"] for w in ws).lower():
                anchors.append((ws[0]["top"], ws))
        anchors.sort()

        for i, (ytop, ws) in enumerate(anchors):
            y_lo = ytop - 24
            y_hi = anchors[i + 1][0] - 6 if i + 1 < len(anchors) else ytop + 40
            block = [w for w in words if y_lo <= w["top"] <= y_hi]
            joined = " ".join(w["text"] for w in block)
            jl = joined.lower()

            avail = "rx" if ("rx" in jl or "prescription" in jl) else "stock"
            category = ("progressive" if "progressive" in jl else
                        "bifocal" if ("bifocal" in jl or "bi focal" in jl) else
                        "single_vision" if "single vision" in jl else None)
            market = self._harvest_market(joined)

            # family = nearest family-column label in y to this anchor row
            fam = None
            best_dy = 999
            for w in fam_col:
                if _clean(w["text"]).lower() == "lens":
                    continue
                dy = abs(w["top"] - ytop)
                if dy <= 30 and dy < best_dy:
                    fam, best_dy = _clean(w["text"]), dy

            # commercial terms = tokens in the technology column band
            terms = set()
            for w in block:
                if not (250 <= cx(w) <= 470):
                    continue
                for tok in re.split(r"[,\s]+", _clean(w["text"]).lower()):
                    tok = tok.strip(" .,+")
                    if tok and tok not in self._REL_STOPWORDS and not _is_pure_number(tok):
                        terms.add(tok)

            if not fam or not category:
                continue
            rel = {"family": fam, "availability": avail, "category": category,
                   "market": market, "terms": terms}
            context.relations.append(rel)
            if fam not in context.family_candidates:
                context.family_candidates.append(fam)

    # ================================================================
    # Geometry-aware extraction for borderless / overprinted tables
    # ================================================================
    def _dedup_overprint_words(self, page):
        """Rebuild the page's words from characters, collapsing GEOMETRIC
        duplicates (a glyph drawn twice at the same coordinates - the
        'IInnddeexx' / 'Astro Astro' overprint artifact). Two *different*
        glyphs at the same x are kept (they are real, e.g. two price layers)."""
        chars = getattr(page, "chars", None) or []
        seen = set()
        uniq = []
        for c in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
            key = (round(c["x0"], 1), round(c["top"], 1), c.get("text", ""))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(c)
        # group into words by line then x-gap
        words = []
        for ws in self._group_chars_to_lines(uniq):
            cur = None
            for c in ws:
                if cur and c["x0"] - cur["x1"] <= 1.6:
                    cur["text"] += c.get("text", "")
                    cur["x1"] = c["x1"]
                else:
                    if cur:
                        words.append(cur)
                    cur = {"text": c.get("text", ""), "x0": c["x0"], "x1": c["x1"],
                           "top": c["top"], "bottom": c.get("bottom", c["top"])}
            if cur:
                words.append(cur)
        return [w for w in words if _clean(w["text"])]

    def _group_chars_to_lines(self, chars, tol=2.2):
        lines = []
        for c in sorted(chars, key=lambda c: (c["top"], c["x0"])):
            if lines and abs(c["top"] - lines[-1][0]) <= tol:
                lines[-1][1].append(c)
            else:
                lines.append((c["top"], [c]))
        return [sorted(cs, key=lambda c: c["x0"]) for _, cs in lines]

    def _cluster_lines(self, words, tol=3.5):
        lines = []
        for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
            if lines and abs(w["top"] - lines[-1][0]) <= tol:
                lines[-1][1].append(w)
            else:
                lines.append((w["top"], [w]))
        return [sorted(ws, key=lambda w: w["x0"]) for _, ws in lines]

    _HEADING_RE = re.compile(
        r"(finished|stock|rx|prescription)\b.*(single\s+vision|progressive|bi\s*focal)"
        r"|(single\s+vision|progressive|bi\s*focal)\b.*(egypt|out\s+of)",
        re.I,
    )

    def _extract_page_tables(self, page):
        """Return [(overrides, header_lines, data_matrix), ...] for a page, using
        the most structurally complete of: line tables -> text tables -> word
        geometry. Candidates are de-duplicated by header + row-content signature."""
        candidates = []  # (score, overrides, header, matrix)

        # A. ruled/line tables
        try:
            for tb in (page.extract_tables() or []):
                m = [[_clean(c) for c in r] for r in tb if r]
                if self._matrix_is_useful(m):
                    candidates.append((self._matrix_score(m), {}, m[:2], m))
        except Exception:
            pass

        # C. text-position tables
        if not candidates:
            try:
                for tb in (page.extract_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "text",
                     "text_tolerance": 3, "min_words_vertical": 2}
                ) or []):
                    m = [[_clean(c) for c in r] for r in tb if r]
                    if self._matrix_is_useful(m):
                        candidates.append((self._matrix_score(m), {}, m[:2], m))
            except Exception:
                pass

        # D. word / character geometry reconstruction (always attempted -
        #    it also segments a page into its heading sections)
        try:
            for ov, hdr, mat in self._reconstruct_sections(page):
                if self._matrix_is_useful(mat) or hdr:
                    candidates.append((self._matrix_score(mat) + 1, ov, hdr, mat))
        except Exception as e:
            self.errors.append(f"geometry reconstruct: {e}")

        # de-dup: keep the highest-scoring candidate per (header sig, row sig)
        best = {}
        for score, ov, hdr, mat in candidates:
            sig = (self._sig(hdr), self._sig(mat[2:] if len(mat) > 2 else mat))
            if sig not in best or score > best[sig][0]:
                best[sig] = (score, ov, hdr, mat)
        return [(ov, hdr, mat) for _, ov, hdr, mat in best.values()]

    def _sig(self, matrix):
        return tuple(tuple(_clean(c).lower() for c in r if _clean(c)) for r in (matrix or []))

    def _matrix_is_useful(self, m):
        """A matrix is commercially useful only if it has a real DATA row - one
        with >=3 filled cells AND at least one numeric cell - not just a header
        or a stray fragment."""
        if not m or len(m) < 2:
            return False
        for r in m[1:]:
            filled = sum(1 for c in r if _clean(c))
            has_num = any(re.search(r"\d", _clean(c)) for c in r)
            if filled >= 2 and has_num:
                return True
        return False

    def _matrix_score(self, m):
        return sum(1 for r in (m or []) for c in r if _clean(c))

    def _reconstruct_sections(self, page):
        """Segment a page into heading-delimited sections and rebuild each as a
        column matrix from word x-geometry."""
        words = self._dedup_overprint_words(page)
        if not words:
            return []
        lines = self._cluster_lines(words)
        sections = []
        cur = None
        for ws in lines:
            joined = _clean(" ".join(w["text"] for w in ws))
            if not joined:
                continue
            if self._HEADING_RE.search(joined) or re.search(
                r"\b(finished|stock|rx)\b.*\b(egypt|out\s+of\s+\w+)\b", joined, re.I
            ):
                if cur and cur["lines"]:
                    sections.append(cur)
                ov = {"new_model": True, "label": joined}
                jl = joined.lower()
                if "rx" in jl or "prescription" in jl:
                    ov["availability"] = "rx"
                elif "finished" in jl or "stock" in jl:
                    ov["availability"] = "stock"
                if "progressive" in jl:
                    ov["category"] = "progressive"
                elif "bi focal" in jl or "bifocal" in jl:
                    ov["category"] = "bifocal"
                elif "single vision" in jl:
                    ov["category"] = "single_vision"
                mk = self._harvest_market(joined)
                if mk:
                    ov["market"] = mk
                cur = {"overrides": ov, "lines": []}
                continue
            if cur is not None:
                cur["lines"].append(ws)
        if cur and cur["lines"]:
            sections.append(cur)

        out = []
        for sec in sections:
            header, matrix = self._lines_to_matrix(sec["lines"])
            if matrix:
                out.append((sec["overrides"], header, matrix))
        return out

    def _lines_to_matrix(self, lines):
        """Cluster all words into columns by x, produce header rows + data rows."""
        allw = [w for ws in lines for w in ws]
        if not allw:
            return [], []
        centers = sorted((w["x0"] + w["x1"]) / 2 for w in allw)
        cols = []           # list of [minx, maxx]
        for c in centers:
            if cols and c - cols[-1][1] <= 26:
                cols[-1][1] = c
            else:
                cols.append([c, c])
        col_mid = [(a + b) / 2 for a, b in cols]

        def col_of(w):
            m = (w["x0"] + w["x1"]) / 2
            return min(range(len(col_mid)), key=lambda i: abs(col_mid[i] - m))

        # first line that carries >=2 numeric cells is the first DATA line
        first_data = 0
        for i, ws in enumerate(lines):
            nums = sum(1 for w in ws if _is_pure_number(w["text"]) or
                       re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", w["text"].replace(",", "")))
            if nums >= 2:
                first_data = i
                break
        header_lines = lines[:first_data] or lines[:1]
        data_lines = lines[first_data:] if first_data else lines

        def to_row(ws):
            row = [""] * len(col_mid)
            for w in ws:
                ci = col_of(w)
                row[ci] = (row[ci] + " " + w["text"]).strip()
            return row

        header = [to_row(ws) for ws in header_lines]
        # merge multi-visual-row headers into one signature row
        merged_hdr = [""] * len(col_mid)
        for hr in header:
            for i, c in enumerate(hr):
                if c:
                    merged_hdr[i] = (merged_hdr[i] + " " + c).strip()
        matrix = [merged_hdr]

        def _is_continuation(ws):
            """A wrapped price/range line: every token is numeric / sign / range
            word, i.e. it carries no identity (coating/design/colour/index) cell."""
            toks = [w["text"] for w in ws]
            if not toks:
                return True
            for t in toks:
                tl = _clean(t).lower()
                if tl in ("to", "-", "+", "±", "/", "|"):
                    continue
                if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?", tl.replace(",", "")):
                    continue
                if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?\s*(?:to|/|~)\s*[+\-]?\d+(?:\.\d+)?", tl):
                    continue
                return False
            return True

        rows = []
        for ws in data_lines:
            r = to_row(ws)
            if rows and _is_continuation(ws):
                for i, c in enumerate(r):
                    if not _clean(c):
                        continue
                    rows[-1][i] = (rows[-1][i] + " " + c).strip() if _clean(rows[-1][i]) else c
            else:
                rows.append(r)
        matrix.extend(rows)
        return header, matrix

    def _section_context(self, base: "ParserContext", overrides: dict) -> "ParserContext":
        c = ParserContext(
            index=base.index, availability=base.availability,
            availability_explicit=base.availability_explicit, market=base.market,
            category=base.category, design_variant=base.design_variant,
            color_variant=base.color_variant,
            family_candidates=list(base.family_candidates),
        )
        c.relations = list(getattr(base, "relations", []))
        if "availability" in overrides:
            c.availability, c.availability_explicit = overrides["availability"], True
        if "category" in overrides:
            c.category = overrides["category"]
        if "market" in overrides:
            c.market = overrides["market"]
        return c

    # ---------------------------------------------------------- section rows
    _NA_CELL = {"", "-", "--", "–", "—", "n/a", "na", "nil"}

    def _rows_from_section(self, header, matrix, ctx: "ParserContext"):
        """Role-aware row builder for a reconstructed section matrix. Handles
        design-name price columns, Total Power/CylN tiers, Sph/Cyl/Price with
        minus/plus sides, add-on rows and row survival."""
        if not matrix or len(matrix) < 2:
            return list(self._parse_table(matrix, ctx)) if matrix else []
        merged = matrix[0]
        ncol = len(merged)
        roles = {}
        designprice = {}
        for i in range(ncol):
            h = _clean(merged[i])
            hl = h.lower()
            if not hl:
                continue
            dv = self._classify_design(h)
            if re.search(r"\bindex\b|\bindx\b", hl):
                roles[i] = "index"
            elif re.search(r"coat", hl):
                roles[i] = "coating"
            elif re.search(r"colou?r|technolog|\btint\b", hl):
                roles[i] = "color"
            elif re.search(r"total\s*power|\bsph\b|sphere", hl):
                roles[i] = "sph"
            elif re.search(r"\bcyl", hl):
                m = re.search(r"cyl\s*-?\s*(\d+(?:\.\d+)?)", hl)
                roles[i] = ("cyltier", float(m.group(1))) if m else "cyl"
            elif dv:
                # a design name in the header -> this column's cells ARE prices for
                # that design, even if the word "Price" also bleeds into the header
                designprice[i] = dv
            elif re.search(r"\bprice\b|/pair|\bcost\b|\bamount\b", hl):
                roles[i] = "price"
            elif re.search(r"\bdesign\b", hl):
                roles[i] = "design"
            elif re.search(r"\bmaterial\b", hl):
                roles[i] = "material"

        price_like = sorted(
            i for i, r in roles.items()
            if r in ("sph", "cyl", "price") or (isinstance(r, tuple) and r[0] == "cyltier")
        )
        # split into side-groups: each 'sph'/'total power' starts a new group
        groups = []
        cur = None
        for i in price_like:
            r = roles[i]
            if r == "sph" or cur is None:
                cur = {"sph": None, "cyl": None, "tiers": [], "price": None}
                groups.append(cur)
            if r == "sph":
                cur["sph"] = i
            elif r == "cyl":
                cur["cyl"] = i
            elif isinstance(r, tuple) and r[0] == "cyltier":
                cur["tiers"].append((i, r[1]))
            elif r == "price":
                cur["price"] = i

        i_index = next((i for i, r in roles.items() if r == "index"), None)
        i_coat = next((i for i, r in roles.items() if r == "coating"), None)
        i_color = next((i for i, r in roles.items() if r == "color"), None)
        i_design = next((i for i, r in roles.items() if r == "design"), None)
        i_mat = next((i for i, r in roles.items() if r == "material"), None)

        section_text = " ".join(_clean(c).lower() for c in merged)
        out = []
        last_index = ctx.index

        for raw in matrix[1:]:
            row = list(raw) + [""] * (ncol - len(raw))

            def cell(i):
                return _clean(row[i]) if i is not None and i < len(row) else ""

            label = cell(0)
            if self._is_addon_label(label) or self._is_addon_label(section_text) and "treatment" in section_text:
                continue
            if any(self._is_addon_label(cell(i)) for i in (i_design, i_color) if i is not None):
                continue

            idxv = self._extract_index(cell(i_index)) if i_index is not None else None
            if idxv:
                last_index = idxv
            index_value = idxv or last_index or ctx.index

            geo = self._classify_geometry(cell(i_design))
            dvar_ctx = self._classify_design(cell(i_design)) or ctx.design_variant
            color_val = None
            color_ambig = False
            if i_color is not None:
                cv = self._classify_color(cell(i_color))
                if cv:
                    color_val = cv
                elif cell(i_color) and not _is_pure_number(cell(i_color)):
                    color_ambig = True
            elif ctx.color_variant:
                color_val = ctx.color_variant
            coating, cstatus, cconf = self._classify_coating(
                cell(i_coat), i_coat is not None, section_text + " " + " ".join(row)
            )

            def base_row():
                r = ExtractedPowerRange(
                    sph_min=0.0, sph_max=0.0, index_value=index_value,
                    availability=ctx.availability if ctx.availability in ("stock", "rx") else "stock",
                    market_scope=ctx.market or None,
                )
                if geo:
                    r.design_type = geo
                    r.is_aspherical = geo in ("aspherical", "double_aspherical")
                r.color_variant = color_val
                r.coating, r.coating_status, r.coating_confidence = coating, cstatus, cconf
                if i_mat is not None and cell(i_mat):
                    r.material = cell(i_mat)
                if color_ambig:
                    r.flag_review("ambiguous colour value")
                return r

            emitted = []
            if designprice:
                for ci, dname in sorted(designprice.items()):
                    v = cell(ci)
                    if v.lower() in self._NA_CELL:
                        continue
                    r = base_row()
                    r.design_variant = dname
                    r.price = self._extract_price(v)
                    if r.price is None:
                        r.flag_review("unresolved / corrupt price cell")
                    emitted.append(r)
            elif groups:
                multi = len(groups) > 1
                for gi, g in enumerate(groups):
                    sign = 0 if not multi else (-1 if gi == 0 else 1)
                    sph_txt = cell(g["sph"]) if g["sph"] is not None else ""
                    sph_rng = self._parse_range(sph_txt)
                    mag = None
                    if sph_rng:
                        mag = max(abs(sph_rng[0]), abs(sph_rng[1]))
                    else:
                        mv = self._extract_price(sph_txt)
                        mag = mv if mv is not None else None
                    if g["tiers"]:
                        for tcol, tlim in g["tiers"]:
                            tv = cell(tcol)
                            if tv.lower() in self._NA_CELL and not tv.strip("-"):
                                continue
                            r = base_row()
                            if mag is not None:
                                if sign < 0:
                                    r.sph_min, r.sph_max = -abs(mag), 0.0
                                elif sign > 0:
                                    r.sph_min, r.sph_max = 0.0, abs(mag)
                                else:
                                    r.sph_min, r.sph_max = -abs(mag), abs(mag)
                                r.has_range = True
                            r.cyl_min, r.cyl_max = -abs(tlim), 0.0
                            r.price = self._extract_price(tv)
                            r.notes = ("minus" if sign < 0 else "plus" if sign > 0 else "band") + f" cyl<={tlim}"
                            if r.price is None:
                                r.flag_review("unresolved / corrupt price cell")
                            emitted.append(r)
                    else:
                        r = base_row()
                        cyl_rng = self._parse_range(cell(g["cyl"])) if g["cyl"] is not None else None
                        if sph_rng:
                            r.sph_min, r.sph_max = sph_rng
                            r.has_range = True
                        elif mag is not None:
                            if sign < 0:
                                r.sph_min, r.sph_max = -abs(mag), 0.0
                            elif sign > 0:
                                r.sph_min, r.sph_max = 0.0, abs(mag)
                            r.has_range = r.sph_min != 0 or r.sph_max != 0
                        if cyl_rng:
                            r.cyl_min, r.cyl_max = cyl_rng
                        r.price = self._extract_price(cell(g["price"])) if g["price"] is not None else None
                        if sign < 0:
                            r.notes = "minus"
                        elif sign > 0:
                            r.notes = "plus"
                        if r.price is None:
                            r.flag_review("unresolved / corrupt price cell")
                        emitted.append(r)
            else:
                emitted = list(self._parse_table([merged, row], ctx))

            for r in emitted:
                # a row must carry at least one piece of real commercial content;
                # a bag of review reasons with nothing else is a mis-detection
                has_content = (
                    r.price is not None or r.has_range or r.design_variant
                    or r.color_variant or r.coating_status in ("resolved", "explicit_none")
                )
                if not has_content:
                    continue
                if r.availability == "stock" and not r.has_range:
                    r.flag_review("STOCK without PowerRange")
                if r.coating_status == "not_found":
                    r.flag_review("coating not_found")
                out.append(r)
        return out

    def _harvest_market(self, text: str) -> Optional[str]:
        """Read a market/geography label from heading text. Generic - the parser
        does not assume a fixed set of markets."""
        for line in (text or "").splitlines():
            s = _clean(line)
            if not s or len(s) > 80:
                continue
            m = re.search(
                r"(?:market|region|geography|area|country|geo)\s*[:\-]\s*([A-Za-z][\w /]+)",
                s, re.I,
            )
            if m:
                return _clean(m.group(1)).title()
            m = re.search(r"\b(?:out\s+of|outside)\s+([A-Za-z]+)\b", s, re.I)
            if m:
                return f"Out Of {m.group(1).title()}"
            m = re.search(r"\b(egypt|ksa|uae|gcc|europe|usa|africa|asia|local|export|domestic|international)\b", s, re.I)
            if m:
                return m.group(1).title()
        return None

    @staticmethod
    def _market_key(market: Optional[str]) -> Optional[str]:
        """Canonical comparison key for a market label so that e.g. 'Outside
        Egypt' and 'Out Of Egypt' compare equal, while 'Egypt' stays distinct."""
        if not market:
            return None
        low = market.lower()
        low = re.sub(r"\b(of|the)\b", " ", low)
        low = re.sub(r"\s+", " ", low).strip()
        outside = bool(re.search(r"\b(out|outside|export|international|abroad)\b", low))
        geo = re.sub(r"\b(out|outside|export|international|abroad|inside|local|domestic)\b", "", low).strip()
        return ("out:" if outside else "") + (geo or low)

    UNRESOLVED_FAMILY = "__UNRESOLVED_FAMILY__"   # keep in sync with models.UNRESOLVED_FAMILY_NAME

    def _resolve_family(self, context: "ParserContext", row_terms: Optional[set] = None) -> Optional[str]:
        """Resolve a product family ONLY from catalog relationship evidence -
        family <-> availability <-> category <-> market <-> commercial terms -
        and ONLY when exactly one family is compatible. Returns None otherwise.
        Price never participates. A pricing-section heading is never a family."""
        row_terms = {str(t).lower() for t in (row_terms or set()) if t}

        rels = [r for r in getattr(context, "relations", []) if r.get("family")]
        if not rels:
            return None

        want_mkt = self._market_key(context.market)

        def mkt_ok(rm):
            k = self._market_key(rm)
            return (k is None) or (want_mkt is None) or (k == want_mkt)

        compat = [
            r for r in rels
            if r.get("availability") in (context.availability, None)
            and r.get("category") in (context.category, None)
            and mkt_ok(r.get("market"))
        ]
        if not compat:
            return None
        fams = {r["family"] for r in compat}
        if len(fams) == 1:
            return fams.pop()
        # >1 compatible family: try to narrow by this row's own commercial terms
        if row_terms:
            narrowed = {
                r["family"] for r in compat
                if r.get("terms") and any(
                    t in rt or rt in t for rt in r["terms"] for t in row_terms
                )
            }
            if len(narrowed) == 1:
                return narrowed.pop()
        return None

    def _assign_family(self, context: "ParserContext", rows: List["ExtractedPowerRange"]) -> str:
        """Resolve the family for a set of rows. When it cannot be resolved from
        relationship evidence the rows are flagged needs_review and the model is
        left explicitly unresolved - the section heading is NEVER used."""
        row_terms = {
            str(v).lower()
            for r in rows for v in (r.coating, r.color_variant, r.design_variant) if v
        }
        fam = self._resolve_family(context, row_terms)
        if fam is not None:
            return fam
        for r in rows:
            r.flag_review("ambiguous/unresolved product family")
        return self.UNRESOLVED_FAMILY

    def _extract_model_name(self, text: str) -> Optional[str]:
        """Extract a product/family name ONLY from an explicit product heading.

        Free-text scanning is deliberately disabled: it produced junk models
        ('Comparison', 'Hazardous', 'CLARITY', ...) from marketing prose. A model
        name now requires an explicit "Lens/Model/Series: <Proper>" label whose
        value is a real proper token (not generic vocabulary)."""
        for raw in (text or "").splitlines():
            s = _clean(raw)
            m = re.match(r"(?:Lens|Lenses|Model|Series)\s*[:\-]\s*([A-Z][A-Za-z0-9 +/\-]{1,24})$", s)
            if m:
                cand = m.group(1).strip()
                if self._looks_like_family(cand):
                    return cand
        return None

    def _extract_index(self, text: str) -> Optional[float]:
        """Read a refractive index. Accepts labelled forms and bare values such
        as 1.5 / 1.53 / 1.56 / 1.74 (a value in [1.40, 1.90])."""
        s = _clean(text)
        m = re.search(r"(?<![\d.])(1\.\d{1,2})(?![\d])", s)
        if m:
            try:
                v = float(m.group(1))
                if 1.40 <= v <= 1.90:
                    return v
            except ValueError:
                pass
        for pattern in self.INDEX_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    return float(match.group(1))
                except:
                    continue
        return None

    def _detect_availability_by_color(self, page) -> Optional[str]:
        """اكتشاف Stock/RX من ألوان الخلايا"""
        if not self.client or cv2 is None or np is None:
            return None

        try:
            # تحويل الصفحة لصورة
            img = page.to_image(resolution=150)
            img_bytes = img.original

            # تحليل الألوان
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_cv is None:
                return None

            # حساب متوسط الألوان
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)

            # نطاقات الألوان
            green_mask = cv2.inRange(hsv, (35, 50, 50), (85, 255, 255))
            red_mask1 = cv2.inRange(hsv, (0, 50, 50), (10, 255, 255))
            red_mask2 = cv2.inRange(hsv, (170, 50, 50), (180, 255, 255))
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)

            green_pixels = cv2.countNonZero(green_mask)
            red_pixels = cv2.countNonZero(red_mask)

            if green_pixels > red_pixels * 2:
                return "stock"
            elif red_pixels > green_pixels * 2:
                return "rx"
            elif green_pixels > 1000 and red_pixels > 1000:
                return "both"

        except Exception as e:
            self.errors.append(f"Color detection error: {e}")

        return None

    # ---------------------------------------------------------- classification
    def _classify_geometry(self, text) -> Optional[str]:
        low = _dedouble(text).lower()
        if not low:
            return None
        for term, canon in OPTICAL_GEOMETRY_TERMS.items():
            if re.search(rf"\b{re.escape(term)}\b", low):
                return canon
        return None

    def _classify_design(self, text) -> Optional[str]:
        """Commercial design line -> design_variant. Never returns geometry."""
        low = _dedouble(text).lower()
        if not low or _is_pure_number(low):
            return None
        for term, canon in DESIGN_VARIANT_TERMS.items():
            if re.search(rf"(?:^|\b|\s){re.escape(term)}(?:\b|\s|$)", low):
                return canon
        # tolerant match for an overprint-garbled "high definition" heading
        if re.search(r"\bhigh\s*def", low):
            return "High Definition"
        return None

    def _classify_color(self, text) -> Optional[str]:
        """Commercial colour / optical-technology cell value. Rejects numbers and
        add-on treatment tokens. Keeps a real suffixed value verbatim."""
        s = _dedouble(text)
        if not s or _is_pure_number(s):
            return None
        low = s.lower()
        if any(t in low for t in ADDON_TREATMENT_TERMS):
            return None
        for root, canon in COLOR_VARIANT_ROOTS.items():
            if low == root or low.startswith(root + "/") or low.startswith(root + " ") or low.startswith(root):
                return s if ("/" in s or " " in s) else canon
        return None

    def _is_addon_label(self, text) -> bool:
        low = _dedouble(text).lower()
        if not low:
            return False
        return any(t in low for t in ADDON_TREATMENT_TERMS)

    def _classify_coating(self, cell, coating_col_present: bool, section_text: str = ""):
        """Return (coating, status, confidence).

        status is one of resolved / explicit_none / not_found. A colour /
        photochromic / polarized term is NEVER treated as a coating.
        """
        if coating_col_present:
            s = _dedouble(cell)
            low = s.lower()
            if not s or low in COATING_NONE_MARKERS:
                return None, "explicit_none", 0.9
            if _is_pure_number(s):
                return None, "not_found", None            # a number here is corrupt
            if self._classify_color(s) or self._classify_geometry(s) or self._classify_design(s):
                return None, "not_found", None            # token belongs to another column
            # any other explicit token in a column explicitly headed "Coating"
            # is a resolved coating (generic - not limited to a hardcoded list)
            return s, "resolved", 0.9
        # no coating column: only a coating HEADING in section text counts
        stext = (section_text or "").lower()
        if "coating" in stext or "treatment" in stext:
            for t in COATING_TERMS:
                if re.search(rf"\b{re.escape(t)}\b", stext):
                    return t.upper(), "resolved", 0.7
        return None, "not_found", None

    def _infer_availability(self, context: "ParserContext", row_text: str) -> str:
        low = _clean(row_text).lower()
        if any(re.search(rf"\b{re.escape(t)}\b", low) for t in AVAILABILITY_RX_TERMS):
            return "rx"
        if any(re.search(rf"\b{re.escape(t)}\b", low) for t in AVAILABILITY_STOCK_TERMS):
            return "stock"
        return context.availability if context.availability in ("stock", "rx") else "stock"

    # ---------------------------------------------------------------- tables
    def _tier_cyl_columns(self, headers) -> List[Tuple[int, float]]:
        """Detect 'Cyl2' / 'Cyl 4' style tier price-band columns -> [(col_idx, cyl_limit)]."""
        out = []
        for i, h in enumerate(headers):
            m = re.fullmatch(r"cyl\s*[-]?\s*(\d+(?:\.\d+)?)", _clean(h).lower())
            if m:
                out.append((i, float(m.group(1))))
        return out

    def _parse_table(self, table, context: "ParserContext"):
        """Parse one table into commercial ExtractedPowerRange rows.

        Preserves the exact Price <-> SPH/CYL association, keeps plus/minus and
        tier bands separate, and never merges two price bands.
        """
        rows_out: List[ExtractedPowerRange] = []
        if not table or len(table) < 2:
            return rows_out

        headers = [_clean(h).lower() if h else "" for h in table[0]]
        sph_col = self._find_col(headers, ["sph", "sphere", "total power", "power", "قوة"])
        cyl_col = self._find_col(headers, ["cyl", "cylinder", "استجماتيزم"])
        add_col = self._find_col(headers, ["add", "addition", "إضافة"])
        index_col = self._find_col(headers, ["index", "indx", "انكسار"])
        price_col = self._find_col(headers, ["price", "cost", "amount", "سعر"])
        material_col = self._find_col(headers, ["material", "مادة", "خامة"])
        design_col = self._find_col(headers, ["design", "تصميم"])
        geometry_col = self._find_col(headers, ["geometry", "surface", "type"])
        color_col = self._find_col(headers, ["color", "colour", "technology", "tech", "tint"])
        coating_col = self._find_col(headers, ["coating", "coat", "treatment"])
        market_col = self._find_col(headers, ["market", "region", "geography", "country", "area"])
        tier_cols = self._tier_cyl_columns(headers)

        section_text = " ".join(headers)

        for raw in table[1:]:
            if not raw or all(not _clean(c) for c in raw):
                continue
            row = list(raw)

            def cell(i):
                return _clean(row[i]) if (i is not None and i < len(row)) else ""

            row_text = " ".join(_clean(c) for c in row)

            # add-on / treatment line -> NO base extraction row at all (item 4/F).
            # Judged from the row LABEL and the design/colour/market columns only,
            # never from an incidental token elsewhere in the row.
            addon_cells = [cell(0)] + [
                cell(i) for i in (design_col, color_col, market_col) if i is not None
            ]
            if any(self._is_addon_label(c) for c in addon_cells):
                continue

            base = ExtractedPowerRange(
                sph_min=0.0, sph_max=0.0,
                index_value=context.index,
                availability=self._infer_availability(context, row_text),
                market_scope=(cell(market_col) or context.market or None),
            )

            # SPH / CYL / ADD
            if sph_col is not None:
                v = self._parse_range(cell(sph_col))
                if v:
                    base.sph_min, base.sph_max = v
                    base.has_range = True
            if cyl_col is not None:
                v = self._parse_range(cell(cyl_col))
                if v:
                    base.cyl_min, base.cyl_max = v
                    base.has_range = True or base.has_range
            if add_col is not None:
                v = self._parse_range(cell(add_col))
                if v:
                    base.add_min, base.add_max = v
            if index_col is not None:
                idx = self._extract_index(cell(index_col))
                if idx:
                    base.index_value = idx
            if material_col is not None and cell(material_col):
                base.material = cell(material_col)

            # design_variant vs design_type (geometry)
            geo = self._classify_geometry(cell(geometry_col)) or self._classify_geometry(cell(design_col))
            if geo:
                base.design_type = geo
                base.is_aspherical = geo in ("aspherical", "double_aspherical")
            dv = self._classify_design(cell(design_col)) or context.design_variant
            if dv:
                base.design_variant = dv                 # commercial "Free Form" lands HERE
            if design_col is not None and cell(design_col) and not dv and not geo:
                base.flag_review("ambiguous design value")

            # colour / optical technology
            if color_col is not None:
                cv = self._classify_color(cell(color_col))
                if cv:
                    base.color_variant = cv
                elif cell(color_col) and not _is_pure_number(cell(color_col)):
                    base.flag_review("ambiguous colour value")
            elif context.color_variant:
                base.color_variant = context.color_variant

            # coating
            coating, cstatus, cconf = self._classify_coating(
                cell(coating_col), coating_col is not None, section_text + " " + row_text
            )
            base.coating, base.coating_status, base.coating_confidence = coating, cstatus, cconf

            # -------- emit rows: one per price band --------
            emitted = []
            if tier_cols:
                for ci, cyl_limit in tier_cols:
                    price = self._extract_price(cell(ci))
                    band = ExtractedPowerRange(**{**base.__dict__, "review_reasons": list(base.review_reasons)})
                    band.cyl_min, band.cyl_max = -abs(cyl_limit), 0.0
                    band.price = price
                    band.notes = f"tier cyl<= {cyl_limit}"
                    if price is None:
                        if _clean(cell(ci)):
                            band.flag_review("unresolved tier price cell")
                        else:
                            continue
                    emitted.append(band)
            else:
                price = self._extract_price(cell(price_col)) if price_col is not None else None
                if price_col is not None and price is None and _clean(cell(price_col)):
                    base.flag_review("unresolved price cell")
                base.price = price
                emitted.append(base)

            for r in emitted:
                if r.price is None and not r.has_range:
                    continue  # neither a price nor a range -> not a product row
                # validation / review state
                if r.availability == "stock" and not r.has_range:
                    r.flag_review("STOCK without PowerRange")
                if r.coating_status == "not_found":
                    r.flag_review("coating not_found")
                # RX without a range is perfectly valid - do NOT flag it
                rows_out.append(r)

        return rows_out

    def _find_col(self, headers, keywords):
        for i, h in enumerate(headers):
            for kw in keywords:
                if kw.lower() in h.lower():
                    return i
        return None

    _RANGE_LIMIT = 40.0   # no optical SPH/CYL/ADD bound is beyond this

    def _parse_range(self, value):
        value = _clean(value).replace("±", "+-")
        m = re.search(
            r"([+-]?\d+\.?\d*)\s*(?:to|~|/)\s*([+-]?\d+\.?\d*)", value, re.I
        ) or re.search(
            r"([+-]?\d+\.?\d*)\s*[-]\s*(?=[+-]?\d)([+-]?\d+\.?\d*)", value
        )
        if m:
            try:
                a, b = float(m.group(1)), float(m.group(2))
                if abs(a) <= self._RANGE_LIMIT and abs(b) <= self._RANGE_LIMIT:
                    return (min(a, b), max(a, b))
            except ValueError:
                pass
        m = re.fullmatch(r"([+-])?\s*(\d+\.?\d*)", value)
        if m:
            try:
                v = float(m.group(2))
                if not (0 < v <= self._RANGE_LIMIT):
                    return None
                if m.group(1) == "-":       # explicit negative bound -> [-v, 0]
                    return (-v, 0.0)
                if m.group(1) == "+":       # explicit positive bound -> [0, +v]
                    return (0.0, v)
                return (-v, v)              # unsigned magnitude -> +/- v
            except ValueError:
                pass
        return None

    def _extract_price(self, value):
        """Accept a price ONLY from a cleanly numeric cell (optionally a currency
        prefix/suffix, thousands separators, whitespace). A cell with stray/garbled
        characters returns None -> the row is later marked needs_review. No
        price-plausibility guessing, no partial-digit recovery."""
        s = _clean(value)
        if not s:
            return None
        had_sep = ("," in s) or bool(re.search(r"\d[.,]\d{3}", s))
        s = re.sub(r"[,\s ]", "", s)
        s = re.sub(r"^(?:egp|le|usd|aed|sar|\$|£|€)\.?", "", s, flags=re.I)
        s = re.sub(r"(?:egp|le|usd|/pair|/pr)$", "", s, flags=re.I)
        if not re.fullmatch(r"\d+(?:\.\d{1,3})?", s):
            return None
        # an un-separated 7+ digit run = two overprinted price layers
        # interleaved into one string (structural integrity, not plausibility)
        if len(s.split(".")[0]) >= 6 and not had_sep:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _consolidate_variants(self):
        """تجميع variants فريدة من power ranges - commercial identity aware."""
        for model in self.extracted_models:
            seen = set()
            for pr in model.power_ranges:
                key = (
                    pr.index_value, pr.material, pr.availability, pr.design_type,
                    pr.is_aspherical, (pr.design_variant or "").lower(),
                    (pr.color_variant or "").lower(), (pr.market_scope or "").lower(),
                )
                if key not in seen:
                    seen.add(key)
                    model.variants.append({
                        "material": pr.material or "CR39",
                        "index_value": pr.index_value or 1.50,
                        "availability": pr.availability,
                        "design_type": pr.design_type,
                        "is_aspherical": pr.is_aspherical,
                        "design_variant": pr.design_variant,
                        "color_variant": pr.color_variant,
                        "market_scope": pr.market_scope,
                    })

    def to_preview_format(self) -> List[Dict[str, Any]]:
        """تحويل لصيغة المعاينة"""
        preview = []
        for i, model in enumerate(self.extracted_models):
            preview.append({
                "id": i,
                "name": model.name,
                "category": model.category,
                "variants_count": len(model.variants),
                "power_ranges_count": len(model.power_ranges),
                "variants": model.variants,
                "sample_ranges": [
                    {
                        "sph": f"[{r.sph_min}, {r.sph_max}]",
                        "cyl": f"[{r.cyl_min}, {r.cyl_max}]",
                        "add": f"[{r.add_min}, {r.add_max}]" if r.add_min else "—",
                        "index": r.index_value,
                        "availability": r.availability,
                        "design_type": r.design_type,
                        "design_variant": r.design_variant,
                        "color_variant": r.color_variant,
                        "market_scope": r.market_scope,
                        "coating_status": r.coating_status,
                        "review_status": r.review_status,
                        "price": r.price,
                    }
                    for r in model.power_ranges[:3]
                ]
            })
        return preview

    _COATING_STATUS_ENUM = {
        "resolved": "RESOLVED",
        "explicit_none": "EXPLICIT_NONE",
        "not_found": "NOT_FOUND",
    }

    def save_extractions_to_db(self, catalog_id: int, db_session):
        """Persist parser output to CatalogExtraction WITHOUT losing any commercial
        identity field (design / colour / market / coating / review state)."""
        from app import models

        for model in self.extracted_models:
            for pr in model.power_ranges:
                cstatus = getattr(
                    models.CoatingExtractionStatus,
                    self._COATING_STATUS_ENUM.get(pr.coating_status, "NOT_FOUND"),
                )
                # Persist range bounds ONLY when the parser actually read an
                # explicit SPH/CYL/ADD range for this row. When has_range is False
                # the dataclass fallbacks (sph 0.0/0.0, cyl -10.0/0.0, ...) are NOT
                # catalog evidence and must be stored as NULL, so downstream
                # confirmation never fabricates a PowerRange (esp. for RX).
                _has_range = bool(pr.has_range)
                extraction = models.CatalogExtraction(
                    catalog_id=catalog_id,
                    extracted_name=model.name,
                    extracted_category=model.category,
                    extracted_material=pr.material,
                    extracted_index=pr.index_value,
                    extracted_availability=pr.availability,
                    extracted_design=pr.design_variant,
                    extracted_color_variant=pr.color_variant,
                    extracted_market_scope=pr.market_scope,
                    extracted_coating=pr.coating,
                    coating_extraction_status=cstatus,
                    coating_confidence=pr.coating_confidence,
                    sph_min=(pr.sph_min if _has_range else None),
                    sph_max=(pr.sph_max if _has_range else None),
                    cyl_min=(pr.cyl_min if _has_range else None),
                    cyl_max=(pr.cyl_max if _has_range else None),
                    add_min=(pr.add_min if _has_range else None),
                    add_max=(pr.add_max if _has_range else None),
                    extracted_price=pr.price,
                    extracted_features=model.features,
                    review_notes=("; ".join(pr.review_reasons) or None),
                    modified_data=(
                        {
                            "design_variant": pr.design_variant,
                            "color_variant": pr.color_variant,
                            "market_scope": pr.market_scope,
                        }
                        if (pr.design_variant or pr.color_variant or pr.market_scope)
                        else None
                    ),
                    status=pr.review_status,   # "pending" (review-ready) or "needs_review"
                )
                db_session.add(extraction)

        db_session.commit()


def preview_pdf_file(pdf_path: str, use_vision: bool = True) -> Dict[str, Any]:
    """معاينة سريعة لملف PDF"""
    parser = PDFHybridParser(use_vision=use_vision)
    extracted = parser.parse_pdf(pdf_path)

    return {
        "success": len(parser.errors) == 0,
        "extracted_models": len(extracted),
        "preview": parser.to_preview_format(),
        "errors": parser.errors
    }
