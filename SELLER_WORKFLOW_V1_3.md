# V1.3 Seller Decision Workflow

Scope: Rx → use mode → customer need → best choice and up to two eligible
alternatives → a short factual explanation. No frame type or frame-aware rule.

## Evidence policy

| Customer need (API key) | Accepted evidence |
| --- | --- |
| `screens_blue_light` | Existing audited `blue_light` registry and its proven, priced add-ons |
| `photochromic_gray` | Existing audited `photo_gray` registry, explicit colour proof required |
| `photochromic_brown` | Existing audited `photo_brown` registry, explicit colour proof required |
| `driving` | SCOPE exact R26 treatment: Night Rider (Blue+Yellow Light, Day/Night Driving) |
| `sun` | SCOPE exact R23/R24/R25 Sun rows |
| `thinner_lens` | SCOPE exact R05: Non Water-Tintable Thin; a catalog descriptor, no predicted thickness |
| `high_impact_resistance` | SCOPE exact R12/R13/R21/R22 HiFlex Impact-Resistant rows; no certification claim |
| `best_optical_clarity` | Unsupported: no sufficient comparative evidence; explicit validation failure |

SCOPE row identities are reconciled from SCOPE.pdf in the permanent
`backend/tests/test_scope_import.py` ROW26 truth set. Exact manufacturer and
treatment matches are required. Material enum defaults, index alone, brand
substrings, colour abbreviations and frame type never prove a need. New registry
entries require a catalog citation and a negative matching test.

Blue/photo combinations remain in secondary advanced controls. An explicit
technology must include the selected need's capability; conflicting selections
fail closed. Existing V1.2 add-on applicability and final pair price composition
are reused without changing their evidence or widening their scope.

## Safety and ranking

1. Validate numeric Rx and cylinder axis; use-mode-specific ADD requirements remain.
2. Validate the use mode, need and technology. Reject conflicting category filters.
3. Reuse existing per-eye eligibility and same-identity pair fulfillment.
4. Require a proven STOCK Egypt / STOCK outside / RX route, single-route price
   provenance, source IDs, currency and a positive finite final pair price.
   Pending price confirmation, review, split fulfillment and unknown market
   cannot enter the seller recommendation list.
5. Rank only accepted pairs using the existing availability-first order, then
   optical score and final pair price. Return at most three distinct identities.

Alternative cards satisfy the same need, category and advanced filters. No
relaxation fallback runs in the seller workflow. Fewer than three eligible
identities means fewer cards, with a clear explanation in the UI.

The reason states verified Rx compatibility, catalog availability, matched
technology, final pair price and recorded index/design. It does not claim medical
benefit, guaranteed real-time inventory, measured thickness or superior clarity.

## Compatibility

The seller UI always sends `customer_need`, including `none`, and an explicit use
mode (distance initially). Existing API callers that omit `customer_need` keep
the legacy informational `best_match` contract. Informational groups retain
base prices and price-confirmation notes; those rows are not seller recommendations.
The new `seller_alternatives` and `seller_recommendation_reason` fields are additive.

## Validation

Permanent regression tests: `backend/tests/test_seller_workflow.py`, alongside
existing use-mode, technology, price caveat and eligibility suites. All testing
uses in-memory fixtures or an isolated copy of `v12_dev.db`; no production DB
or schema migration is required. The frontend build and real browser checks
must pass before creating `v1.3.0`.

Release validation completed: 89 targeted backend tests; full backend regression
1101 passed; 4 frontend API contract tests passed; production build compiled
successfully. Real catalog verification covered 36 searches on an isolated
`v12_dev.db` copy. A real Edge browser verified prescription creation and 11
seller searches, visible reasons and alternatives, use-mode category boundaries,
and the disabled unsupported clarity option, with no page errors.

The frontend API contract regression lives in `dashboard/src/services/api.test.js`:
it prevents `customer_need` from being dropped before reaching the backend.

Known dependency limitation: the existing lockfile installation reported 32 npm
audit findings (9 low, 9 moderate, 14 high). V1.3 does not update dependencies.
