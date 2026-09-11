"""Generic index-column price-grid strategy.

Recognises a price table whose shape is:

    row attributes  (family block  ->  treatment band  ->  coating label)
    x  column axis   (refractive-index headers repeated once per family block)
    ->  cell         (one retail *pair* price per (attributes, index))

Everything here is GEOMETRIC and manufacturer-agnostic. There are NO
manufacturer / brand / product literals: the grid is discovered from word
x/y geometry, the family and treatment band labels are read from the page's own
heading rows, and the commercial context (category / availability / market /
currency) is supplied by the caller from the section heading it already
tracks. If the structural signature of an index-column grid is not clearly
present the strategy returns nothing and the caller falls through to the
existing strategies.

`GridPolicy` exposes only generic knobs (token shapes, geometry tolerances,
near-tie tolerance, the caller-resolved context). Swap the policy and the same
code parses any "attributes-in-rows x index-in-columns -> price" grid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Optional, Tuple


@dataclass
class GridPolicy:
    # a refractive-index column header token (generic: 1.xx / 2.xx)
    index_token_re: str = r"^[12]\.\d{1,2}$"
    # tokens that mark "no product in this cell"
    unavailable_tokens: tuple = ("-", "–", "—", "−", "n/a", "na")
    # a price cell: plain 3-7 digits OR grouped thousands (never a decimal)
    price_token_re: str = r"^\d{1,3}(?:,\d{3})+$|^\d{3,7}$"
    price_min: int = 100
    # a coating-row leading label must match this (default: any non-empty label)
    coating_label_re: str = r".+"
    # commercial context resolved by the caller FROM THE SECTION HEADING
    category: Optional[str] = None
    availability: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None
    # geometry tolerances
    col_assign_tol: float = 22.0       # px: max |x_center(price) - x_center(column)|
    near_tie_tolerance: float = 4.0    # px: 2nd-nearest column within this of the
                                      # nearest -> ambiguous, refuse to guess
    line_y_tol: float = 3.0           # px: word-top delta that is "same line"
    index_group_gap: float = 70.0     # px: x-gap that separates two family blocks'
                                      # repeated index-header runs on one line
    band_max_tokens: int = 5          # a stand-alone treatment-band header is short
    # structural-evidence gate
    min_family_blocks: int = 1
    min_index_cols: int = 3           # a single-block grid needs >= this many cols
    min_data_rows: int = 2


@dataclass
class GridRow:
    family: Optional[str]
    tier: Optional[str]                # commercial tier within `family`; None
                                       # unless a shared-family split was proven
    treatment_band: Optional[str]
    coating: Optional[str]
    index_value: Optional[float]
    price_pair: Optional[Decimal]
    currency: Optional[str]
    category: Optional[str]
    availability: Optional[str]
    market: Optional[str]
    status: str                       # "ok" | "needs_review"
    review_reasons: List[str] = field(default_factory=list)
    evidence: Dict = field(default_factory=dict)


# --------------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _xc(w: dict) -> float:
    return (w["x0"] + w["x1"]) / 2.0


def _cluster_lines(words: List[dict], y_tol: float) -> List[List[dict]]:
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for ln in lines:
            if abs(ln[0]["top"] - w["top"]) <= y_tol:
                ln.append(w)
                break
        else:
            lines.append([w])
    for ln in lines:
        ln.sort(key=lambda w: w["x0"])
    lines.sort(key=lambda ln: ln[0]["top"])
    return lines


def _leading_text(line: List[dict], stop_x: Optional[float] = None) -> str:
    out = []
    for w in line:
        if stop_x is not None and w["x0"] >= stop_x:
            break
        if re.fullmatch(r"[\d.,–—−-]+", w["text"]):
            break
        out.append(w["text"])
    return _norm(" ".join(out))


def _segments_by_gap(words: List[dict], gap: float) -> List[List[dict]]:
    """Split an x-sorted word run wherever the gap to the next word exceeds `gap`."""
    if not words:
        return []
    segs = [[words[0]]]
    for prev, cur in zip(words, words[1:]):
        if cur["x0"] - prev["x1"] > gap:
            segs.append([])
        segs[-1].append(cur)
    return segs


def _looks_like_band(text: str, max_tokens: int) -> bool:
    toks = text.split()
    if not toks or len(toks) > max_tokens:
        return False
    if any(re.search(r"\d", t) for t in toks):
        return False
    return any(any(ch.isalpha() for ch in t) for t in toks)


# --------------------------------------------------------------------- detection
def detect_index_grid(page, policy: Optional[GridPolicy] = None) -> bool:
    """True only when the page geometrically carries an index-column price grid:
    a line with one or more runs of >= 2 index-header tokens, plus >= min_data_rows
    lines beneath that carry price cells alignable to those columns."""
    policy = policy or GridPolicy()
    try:
        words = page.extract_words(x_tolerance=1.2, y_tolerance=2, keep_blank_chars=False)
    except Exception:
        return False
    hdr = _find_grid_header(words, policy)
    if hdr is None:
        return False
    _, groups, _ = hdr
    cols_total = sum(len(g) for g in groups)
    if len(groups) < policy.min_family_blocks:
        return False
    if len(groups) == 1 and cols_total < policy.min_index_cols:
        return False
    price_re = re.compile(policy.price_token_re)
    hdr_y = hdr[0]
    data_rows = 0
    for ln in _cluster_lines(words, policy.line_y_tol):
        if ln[0]["top"] <= hdr_y:
            continue
        if any(price_re.fullmatch(w["text"].replace(",", "")) for w in ln):
            data_rows += 1
    return data_rows >= policy.min_data_rows


# --------------------------------------------------------------------- core
def _find_grid_header(words, policy) -> Optional[Tuple[float, List[List[dict]], List[dict]]]:
    """Return (y, index_groups, line_words) for the line that has the most runs of
    >= 2 refractive-index tokens; None if there is no such line."""
    idx_re = re.compile(policy.index_token_re)
    best = None
    for ln in _cluster_lines(words, policy.line_y_tol):
        idx_words = [w for w in ln if idx_re.fullmatch(w["text"])]
        if len(idx_words) < 2:
            continue
        groups = [g for g in _segments_by_gap(idx_words, policy.index_group_gap)
                  if len(g) >= 2]
        if not groups:
            continue
        if best is None or len(groups) > len(best[1]) or (
            len(groups) == len(best[1])
            and sum(len(g) for g in groups) > sum(len(g) for g in best[1])
        ):
            best = (ln[0]["top"], groups, ln)
    return best


def _family_headings(lines, hdr_y, n_blocks, policy):
    """Nearest heading row above the grid header that splits into >= n_blocks
    gap-separated text segments -> [(name, x0), ...]; [] if none is found."""
    idx_re = re.compile(policy.index_token_re)
    price_re = re.compile(policy.price_token_re)
    for ln in sorted((l for l in lines if l[0]["top"] < hdr_y),
                     key=lambda l: -l[0]["top"]):
        if any(idx_re.fullmatch(w["text"]) or price_re.fullmatch(w["text"].replace(",", ""))
               for w in ln):
            continue
        segs = _segments_by_gap(ln, policy.index_group_gap)
        alpha_segs = [s for s in segs
                      if any(any(ch.isalpha() for ch in w["text"]) for w in s)]
        if len(alpha_segs) >= n_blocks:
            return [(_norm(" ".join(w["text"] for w in s)), s[0]["x0"])
                    for s in alpha_segs[:n_blocks]]
    return []


def _split_family_tier(names: List[Optional[str]]) -> Dict[str, Tuple[str, Optional[str]]]:
    """Generic family/tier decomposition, PROVEN by the document's own labels -
    never invented. Group the family-heading labels found on this page by their
    shared FIRST token: a group with >= 2 DISTINCT labels proves a shared family
    with sibling tiers (family = the shared first token, tier = the remainder of
    each label); a group of size 1 has no sibling to prove a split against, so
    the whole label is kept as `family` and `tier` stays None.

    e.g. {"ClearMind Individual 3", "ClearMind Superb"} -> both split into
    family "ClearMind" + tier "Individual 3" / "Superb"; "ClearView RX" and
    "SPH RX" each stand alone -> kept whole, tier=None."""
    groups: Dict[str, set] = {}
    for n in names:
        if not n:
            continue
        first = n.split(" ", 1)[0]
        groups.setdefault(first, set()).add(n)
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for n in names:
        if not n:
            continue
        first, _, rest = n.partition(" ")
        if rest and len(groups.get(first, ())) >= 2:
            out[n] = (first, rest)
        else:
            out[n] = (n, None)
    return out


def parse_index_grid(page, policy: GridPolicy) -> List[GridRow]:
    """Parse an index-column price grid off a pdfplumber page. Returns [] when the
    structural signature is not clearly present (caller then falls through)."""
    try:
        words = page.extract_words(x_tolerance=1.2, y_tolerance=2, keep_blank_chars=False)
    except Exception:
        return []
    if not words:
        return []

    idx_re = re.compile(policy.index_token_re)
    price_re = re.compile(policy.price_token_re)
    coat_re = re.compile(policy.coating_label_re)
    unavail = {t.lower() for t in policy.unavailable_tokens}
    page_w = getattr(page, "width", None) or max(w["x1"] for w in words)
    page_no = getattr(page, "page_number", None)

    hdr = _find_grid_header(words, policy)
    if hdr is None:
        return []
    hdr_y, groups, _ = hdr
    cols_total = sum(len(g) for g in groups)
    if len(groups) < policy.min_family_blocks:
        return []
    if len(groups) == 1 and cols_total < policy.min_index_cols:
        return []

    lines = _cluster_lines(words, policy.line_y_tol)
    fam_head = _family_headings(lines, hdr_y, len(groups), policy)

    # block x-intervals: prefer the family-heading segment x0 (captures the row
    # label column that sits LEFT of the first index token); else fall back to
    # the index-group x0 and leave the family name unresolved.
    blocks = []  # (name, x0, x1, seed_columns)
    for k, g in enumerate(groups):
        seed_cols = {float(w["text"]): _xc(w) for w in g}
        if fam_head and k < len(fam_head):
            name = fam_head[k][0]
            bx0 = fam_head[k][1] - 2.0
        else:
            name = None
            bx0 = g[0]["x0"] - 2.0
        if fam_head and k + 1 < len(fam_head):
            bx1 = fam_head[k + 1][1] - 1.0
        elif k + 1 < len(groups):
            bx1 = groups[k + 1][0]["x0"] - 1.0
        else:
            bx1 = page_w
        blocks.append((name, bx0, bx1, seed_cols))

    # family/tier decomposition, proven ONLY from the block labels found on THIS
    # page (a family with a sibling tier elsewhere never leaks in) - see
    # _split_family_tier. A block whose name could not be resolved keeps
    # (None, None): family stays unresolved, tier is never guessed for it.
    fam_tier = _split_family_tier([b[0] for b in blocks])

    rows: List[GridRow] = []
    for raw_name, bx0, bx1, seed_cols in blocks:
        family, tier = fam_tier.get(raw_name, (raw_name, None))
        bwords = [w for w in words if bx0 <= _xc(w) < bx1 and w["top"] >= hdr_y - policy.line_y_tol]
        blines = _cluster_lines(bwords, policy.line_y_tol)

        columns: Dict[float, float] = dict(seed_cols)
        treatment_band: Optional[str] = None
        seen_row: Dict[tuple, int] = {}
        row_slots: Dict[tuple, list] = {}

        for ln in blines:
            joined = _norm(" ".join(w["text"] for w in ln))
            idx_hits = [w for w in ln if idx_re.fullmatch(w["text"])]

            # (a) index-header line -> (re)build the column map for this block
            if len(idx_hits) >= 2:
                columns = {float(w["text"]): _xc(w) for w in idx_hits}
                lead = _leading_text(ln, stop_x=idx_hits[0]["x0"])
                if lead and _looks_like_band(lead, policy.band_max_tokens):
                    treatment_band = lead
                continue

            cells = [w for w in ln
                     if price_re.fullmatch(w["text"].replace(",", ""))
                     or w["text"].lower() in unavail]
            lead = _leading_text(ln)

            # (b) stand-alone treatment-band line (label, no price cells)
            if lead and not cells:
                if _looks_like_band(joined, policy.band_max_tokens):
                    treatment_band = joined
                continue

            # (c) coating data row
            if not (lead and cells and columns and coat_re.match(lead)):
                continue
            row_key = (family, tier, treatment_band, lead)
            seen_row[row_key] = seen_row.get(row_key, 0) + 1
            row_slots.setdefault(row_key, [])
            for cw in cells:
                if cw["text"].lower() in unavail:
                    continue
                ranked = sorted((abs(_xc(cw) - cx), iv) for iv, cx in columns.items())
                best_d, best_idx = ranked[0] if ranked else (1e9, None)
                second_d = ranked[1][0] if len(ranked) > 1 else None
                second_idx = ranked[1][1] if len(ranked) > 1 else None
                reasons: List[str] = []
                if best_idx is None or best_d > policy.col_assign_tol:
                    reasons.append(f"price {cw['text']} not alignable to an index column "
                                   f"(nearest {best_idx} @ {best_d:.0f}px)")
                elif (second_d is not None
                      and second_d <= policy.col_assign_tol
                      and (second_d - best_d) <= policy.near_tie_tolerance):
                    reasons.append(
                        f"ambiguous index-column alignment: price {cw['text']} is "
                        f"{best_d:.1f}px from {best_idx} and {second_d:.1f}px from "
                        f"{second_idx} (<= near_tie_tolerance {policy.near_tie_tolerance})")
                    best_idx = None
                if treatment_band is None:
                    reasons.append("no treatment band in context")
                if family is None:
                    reasons.append("family/section heading not found for this block")
                try:
                    price = Decimal(cw["text"].replace(",", ""))
                except Exception:
                    price = None
                    reasons.append(f"unparseable price {cw['text']!r}")
                if price is not None and price < policy.price_min:
                    reasons.append(f"price {price} below floor {policy.price_min}")
                if policy.currency is None:
                    reasons.append("currency not stated on page")
                rows.append(GridRow(
                    family=family, tier=tier, treatment_band=treatment_band, coating=lead,
                    index_value=best_idx, price_pair=price,
                    currency=policy.currency, category=policy.category,
                    availability=policy.availability, market=policy.market,
                    status="ok" if not reasons else "needs_review",
                    review_reasons=list(reasons),
                    evidence={"page": page_no, "y": round(ln[0]["top"], 1),
                              "price_x": round(_xc(cw), 1),
                              "col_x": round(columns.get(best_idx, -1), 1),
                              "raw_row": joined[:160]}))
                row_slots[row_key].append(len(rows) - 1)

        # re-flow guard: a (family, tier, treatment_band, coating) that repeats inside
        # one block means a second section re-flowed into this x-interval -> we
        # can no longer prove which section each row belongs to.
        for rk, cnt in seen_row.items():
            if cnt > 1:
                for ri in row_slots[rk]:
                    r = rows[ri]
                    if "layout re-flow" not in " ".join(r.review_reasons):
                        r.review_reasons.append(
                            f"layout re-flow: '{rk[3]}' appears {cnt}x in one "
                            f"'{rk[2]}' block - family/section association not provable")
                        r.status = "needs_review"

    return rows
