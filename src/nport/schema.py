"""Programmatic data schema for N-PORT holdings CSV columns.

Documents every CSV column, its type, and when it's required.
Used by the ``nport schema`` CLI command and available for
programmatic introspection.
"""

from __future__ import annotations

from dataclasses import dataclass

from nport.config import HOLDINGS_KEY_MAP


@dataclass(frozen=True)
class FieldSpec:
    """Specification for a single holding field."""

    name: str  # snake_case dataclass field name
    csv_header: str  # camelCase CSV column name
    group: str  # logical group
    required: str  # "always", "optional", or "conditional"
    condition: str  # when required=="conditional", describes the condition
    value_type: str  # lexical type enforced before XML serialization
    description: str


# ── Build the master list ─────────────────────────────────

_FIELD_TO_CSV = {v: k for k, v in HOLDINGS_KEY_MAP.items()}

_SPEC_DEFS: list[tuple[str, str, str, str, str, str, str]] = [
    # (group, required, condition, value_type, description)  — keyed by field name
    # ── base (20) ──
    ("name", "base", "always", "", "str", "Issuer name"),
    ("lei", "base", "always", "", "str", "LEI (20-char or N/A)"),
    ("title", "base", "always", "", "str", "Security title"),
    ("cusip", "base", "always", "", "str", "CUSIP (9-char, N/A, or 000000000)"),
    ("isin", "base", "optional", "", "str", "ISIN (12-char, optional)"),
    ("ticker", "base", "optional", "", "str", "Ticker symbol (optional)"),
    ("balance", "base", "always", "", "decimal", "Number of shares/units/par"),
    ("units", "base", "always", "", "enum", "Units: NS, PA, NC, OU"),
    ("cur_cd", "base", "always", "", "str", "ISO currency code"),
    ("val_usd", "base", "always", "", "decimal", "Value in USD"),
    ("pct_val", "base", "always", "", "decimal", "Percent of net assets"),
    ("payoff_profile", "base", "always", "", "enum", "Long, Short, or N/A"),
    ("asset_cat", "base", "always", "", "enum", "Asset category (20 values)"),
    ("issuer_cat", "base", "always", "", "enum", "Issuer category (9 values)"),
    ("inv_country", "base", "always", "", "str", "ISO country code (2-char)"),
    ("is_restricted_sec", "base", "always", "", "Y/N", "Is restricted security"),
    ("fair_val_level", "base", "always", "", "enum", "Fair value level: 1, 2, 3, N/A"),
    ("is_cash_collateral", "base", "always", "", "Y/N", "Is cash collateral"),
    ("is_non_cash_collateral", "base", "always", "", "Y/N", "Is non-cash collateral"),
    ("is_loan_by_fund", "base", "always", "", "Y/N", "Is loan by fund"),
    # ── conditional (5) ──
    ("issuer_conditional_desc", "conditional", "conditional", "issuerCat==OTHER", "str", "Issuer conditional description"),
    ("asset_conditional_desc", "conditional", "conditional", "assetCat==OTHER", "str", "Asset conditional description"),
    ("other_desc", "conditional", "optional", "", "str", "Other identifier description"),
    ("other_value", "conditional", "optional", "", "str", "Other identifier value"),
    ("exchange_rt", "conditional", "conditional", "non-USD currency", "decimal", "Exchange rate to USD"),
    # ── debt (6) ──
    ("maturity_dt", "debt", "conditional", "debt security", "date", "Maturity date"),
    ("coupon_kind", "debt", "conditional", "debt security", "enum", "Fixed, Floating, Variable, None"),
    ("annualized_rt", "debt", "conditional", "debt security", "decimal", "Annualized rate"),
    ("is_default", "debt", "conditional", "debt security", "Y/N", "Is in default"),
    ("are_intrst_pmnts_in_arrs", "debt", "conditional", "debt security", "Y/N", "Are interest payments in arrears"),
    ("is_paid_kind", "debt", "conditional", "debt security", "Y/N", "Is paid in kind"),
    # ── deriv_common (4) ──
    ("deriv_cat", "deriv_common", "conditional", "derivative holding", "enum", "FWD, FUT, SWP, OPT, SWO, WAR, OTH"),
    ("counterparty_name", "deriv_common", "conditional", "derivCat set", "str", "Counterparty name"),
    ("counterparty_lei", "deriv_common", "conditional", "derivCat set", "str", "Counterparty LEI"),
    ("unrealized_appr", "deriv_common", "conditional", "derivCat set", "decimal", "Unrealized appreciation"),
    # ── option (7) ──
    ("put_or_call", "option", "conditional", "derivCat in OPT/SWO/WAR", "enum", "Put or Call"),
    ("written_or_pur", "option", "conditional", "derivCat in OPT/SWO/WAR", "enum", "Written or Purchased"),
    ("share_no", "option", "conditional", "derivCat in OPT/SWO/WAR", "decimal", "Number of shares"),
    ("exercise_price", "option", "conditional", "derivCat in OPT/SWO/WAR", "decimal", "Exercise price"),
    ("exercise_price_cur_cd", "option", "conditional", "derivCat in OPT/SWO/WAR", "str", "Exercise price currency"),
    ("exp_dt", "option", "conditional", "derivCat in OPT/SWO/WAR/FWD/FUT", "date", "Expiration date"),
    ("delta", "option", "conditional", "derivCat in OPT/SWO/WAR/OTH", "decimal", "Delta (or N/A)"),
    # ── ref_instrument (8) ──
    ("ref_inst_type", "ref_instrument", "conditional", "option, swaption, warrant, or future", "enum", "indexBasket or otherRefInst"),
    ("ref_index_name", "ref_instrument", "conditional", "refInstType==indexBasket", "str", "Reference index name"),
    ("ref_index_identifier", "ref_instrument", "conditional", "refInstType==indexBasket", "str", "Reference index identifier"),
    ("ref_issuer_name", "ref_instrument", "conditional", "refInstType==otherRefInst", "str", "Reference issuer name"),
    ("ref_issue_title", "ref_instrument", "conditional", "refInstType==otherRefInst", "str", "Reference issue title"),
    ("ref_cusip", "ref_instrument", "optional", "", "str", "Reference CUSIP"),
    ("ref_isin", "ref_instrument", "optional", "", "str", "Reference ISIN"),
    ("ref_ticker", "ref_instrument", "optional", "", "str", "Reference ticker"),
    # ── swap (30) ──
    ("swap_flag", "swap", "conditional", "derivCat==SWP", "Y/N", "Swap flag (Y/N)"),
    ("termination_dt", "swap", "conditional", "derivCat in SWP/OTH", "date", "Termination date"),
    ("upfront_pmnt", "swap", "conditional", "derivCat==SWP", "decimal", "Upfront payment"),
    ("pmnt_cur_cd", "swap", "conditional", "derivCat==SWP", "str", "Payment currency code"),
    ("upfront_rcpt", "swap", "conditional", "derivCat==SWP", "decimal", "Upfront receipt"),
    ("rcpt_cur_cd", "swap", "conditional", "derivCat==SWP", "str", "Receipt currency code"),
    ("notional_amt", "swap", "conditional", "derivCat in SWP/FWD/FUT/OTH", "decimal", "Notional amount"),
    ("swap_cur_cd", "swap", "conditional", "derivCat in SWP/FWD/FUT/OTH", "str", "Derivative currency code"),
    ("rec_fixed_or_floating", "swap", "conditional", "derivCat==SWP", "enum", "Fixed, Floating, or Other"),
    ("rec_fixed_rt", "swap", "conditional", "recFixedOrFloating==Fixed", "decimal", "Receive fixed rate"),
    ("rec_floating_rt_index", "swap", "conditional", "recFixedOrFloating==Floating", "str", "Receive floating rate index"),
    ("rec_floating_rt_spread", "swap", "conditional", "recFixedOrFloating==Floating", "decimal", "Receive floating rate spread"),
    ("rec_pmnt_amt", "swap", "conditional", "receive leg Fixed/Floating", "decimal", "Receive payment amount"),
    ("rec_cur_cd", "swap", "conditional", "receive leg Fixed/Floating", "str", "Receive currency code"),
    ("rec_rate_tenor", "swap", "conditional", "receive leg Floating", "enum", "Receive rate tenor: Day, Month, or Year"),
    ("rec_rate_unit", "swap", "conditional", "receive leg Floating", "nonnegative integer", "Receive rate-tenor unit (up to 5 digits)"),
    ("rec_reset_dt", "swap", "conditional", "receive leg Floating", "enum", "Receive reset date unit: Day, Month, or Year"),
    ("rec_reset_unit", "swap", "conditional", "receive leg Floating", "nonnegative integer", "Receive reset-date unit (up to 5 digits)"),
    ("rec_desc", "swap", "conditional", "receive leg Other", "str", "Receive leg description"),
    ("pmnt_fixed_or_floating", "swap", "conditional", "derivCat==SWP", "enum", "Fixed, Floating, or Other"),
    ("pmnt_fixed_rt", "swap", "conditional", "pmntFixedOrFloating==Fixed", "decimal", "Pay fixed rate"),
    ("pmnt_floating_rt_index", "swap", "conditional", "pmntFixedOrFloating==Floating", "str", "Pay floating rate index"),
    ("pmnt_floating_rt_spread", "swap", "conditional", "pmntFixedOrFloating==Floating", "decimal", "Pay floating rate spread"),
    ("pmnt_pmnt_amt", "swap", "conditional", "payment leg Fixed/Floating", "decimal", "Pay payment amount"),
    ("pmnt_cur_cd_leg", "swap", "conditional", "payment leg Fixed/Floating", "str", "Pay leg currency code"),
    ("pmnt_rate_tenor", "swap", "conditional", "payment leg Floating", "enum", "Pay rate tenor: Day, Month, or Year"),
    ("pmnt_rate_unit", "swap", "conditional", "payment leg Floating", "nonnegative integer", "Pay rate-tenor unit (up to 5 digits)"),
    ("pmnt_reset_dt", "swap", "conditional", "payment leg Floating", "enum", "Pay reset date unit: Day, Month, or Year"),
    ("pmnt_reset_unit", "swap", "conditional", "payment leg Floating", "nonnegative integer", "Pay reset-date unit (up to 5 digits)"),
    ("pmnt_desc", "swap", "conditional", "payment leg Other", "str", "Pay leg description"),
    # ── forward (1) ──
    ("payoff_prof_deriv", "forward", "conditional", "derivCat in FWD/FUT", "enum", "Long, Short, or N/A"),
    # ── other_deriv (1) ──
    ("other_deriv_desc", "other_deriv", "conditional", "derivCat==OTH", "str", "Other derivative description"),
    # C.7 is policy-conditional and must originate in the internal liquidity program.
    ("liquidity_classification_json", "liquidity", "conditional", "fund policy requires C.7", "json", "One to four HLI/MLI/LLI/ILI categories, or N/A"),
    ("liquidity_circumstances_json", "liquidity", "optional", "", "json", "Up to three liquidity circumstances"),
]


def _build_field_specs() -> list[FieldSpec]:
    specs = []
    for entry in _SPEC_DEFS:
        name, group, required, condition, value_type, description = entry
        csv_header = _FIELD_TO_CSV.get(name, name)
        specs.append(FieldSpec(
            name=name,
            csv_header=csv_header,
            group=group,
            required=required,
            condition=condition,
            value_type=value_type,
            description=description,
        ))
    return specs


FIELD_SPECS: list[FieldSpec] = _build_field_specs()

FIELD_BY_NAME: dict[str, FieldSpec] = {s.name: s for s in FIELD_SPECS}

DEBT_ASSET_CATEGORIES = frozenset({"DBT", "ABS-MBS", "ABS-CBDO", "ABS-O"})
DEBT_FIELD_NAMES = frozenset(
    spec.name for spec in FIELD_SPECS if spec.group == "debt"
)
DERIVATIVE_GROUPS = frozenset({
    "deriv_common", "option", "ref_instrument", "swap", "forward", "other_deriv",
})
DERIVATIVE_FIELD_NAMES = frozenset(
    spec.name for spec in FIELD_SPECS if spec.group in DERIVATIVE_GROUPS
)


def _fields_in_groups(*groups: str) -> set[str]:
    return {spec.name for spec in FIELD_SPECS if spec.group in groups}


def get_allowed_derivative_fields(deriv_cat: str) -> frozenset[str]:
    """Return derivative model fields serialized by the selected XML branch."""
    common = _fields_in_groups("deriv_common", "ref_instrument")
    if deriv_cat in {"OPT", "SWO", "WAR"}:
        branch = _fields_in_groups("option")
    elif deriv_cat == "SWP":
        branch = _fields_in_groups("swap")
    elif deriv_cat in {"FWD", "FUT"}:
        branch = _fields_in_groups("forward") | {
            "exp_dt", "notional_amt", "swap_cur_cd",
        }
    elif deriv_cat == "OTH":
        branch = _fields_in_groups("other_deriv") | {
            "termination_dt", "notional_amt", "swap_cur_cd", "delta",
        }
    else:
        branch = set()
    return frozenset(common | branch)


def get_required_fields(
    deriv_cat: str = "", has_debt: bool = False, *,
    ref_inst_type: str = "", rec_fixed_or_floating: str = "",
    pmnt_fixed_or_floating: str = "", currency: str = "",
) -> list[str]:
    """Return list of required field names for a given holding type.

    Args:
        deriv_cat: Derivative category (e.g. "OPT", "SWP", "FWD"), or "" for non-derivative.
        has_debt: Whether the holding is a debt security.
        ref_inst_type: Selected derivative reference-instrument branch.
        rec_fixed_or_floating: Selected swap receipt-leg branch.
        pmnt_fixed_or_floating: Selected swap payment-leg branch.
        currency: Holding currency; non-USD positions require an exchange rate.

    Returns:
        List of snake_case field names that are required.
    """
    required = {spec.name for spec in FIELD_SPECS if spec.required == "always"}

    if has_debt:
        required.update({
            "maturity_dt", "coupon_kind", "annualized_rt", "is_default",
            "are_intrst_pmnts_in_arrs", "is_paid_kind",
        })

    if currency and currency != "USD":
        required.add("exchange_rt")

    if deriv_cat:
        required.update({
            "deriv_cat", "counterparty_name", "counterparty_lei", "unrealized_appr",
        })

    if deriv_cat in {"OPT", "SWO", "WAR"}:
        required.update({
            "put_or_call", "written_or_pur", "share_no", "exercise_price",
            "exercise_price_cur_cd", "exp_dt", "delta", "ref_inst_type",
        })
    elif deriv_cat in {"FWD", "FUT"}:
        required.update({"payoff_prof_deriv", "exp_dt", "notional_amt", "swap_cur_cd"})
        if deriv_cat == "FUT":
            required.add("ref_inst_type")
    elif deriv_cat == "SWP":
        required.update({
            "swap_flag", "termination_dt", "upfront_pmnt", "pmnt_cur_cd",
            "upfront_rcpt", "rcpt_cur_cd", "notional_amt", "swap_cur_cd",
            "rec_fixed_or_floating", "pmnt_fixed_or_floating",
        })
        if rec_fixed_or_floating == "Fixed":
            required.update({"rec_fixed_rt", "rec_pmnt_amt", "rec_cur_cd"})
        elif rec_fixed_or_floating == "Floating":
            required.update({
                "rec_floating_rt_index", "rec_floating_rt_spread", "rec_pmnt_amt",
                "rec_cur_cd", "rec_rate_tenor", "rec_rate_unit", "rec_reset_dt",
                "rec_reset_unit",
            })
        elif rec_fixed_or_floating == "Other":
            required.add("rec_desc")
        if pmnt_fixed_or_floating == "Fixed":
            required.update({"pmnt_fixed_rt", "pmnt_pmnt_amt", "pmnt_cur_cd_leg"})
        elif pmnt_fixed_or_floating == "Floating":
            required.update({
                "pmnt_floating_rt_index", "pmnt_floating_rt_spread", "pmnt_pmnt_amt",
                "pmnt_cur_cd_leg", "pmnt_rate_tenor", "pmnt_rate_unit",
                "pmnt_reset_dt", "pmnt_reset_unit",
            })
        elif pmnt_fixed_or_floating == "Other":
            required.add("pmnt_desc")
    elif deriv_cat == "OTH":
        required.update({
            "other_deriv_desc", "termination_dt", "notional_amt", "swap_cur_cd", "delta",
        })

    if ref_inst_type == "indexBasket":
        required.update({"ref_index_name", "ref_index_identifier"})
    elif ref_inst_type == "otherRefInst":
        required.update({"ref_issuer_name", "ref_issue_title"})

    return [spec.name for spec in FIELD_SPECS if spec.name in required]


def print_schema() -> None:
    """Print a human-readable table of the data schema."""
    # Group fields
    groups: dict[str, list[FieldSpec]] = {}
    for spec in FIELD_SPECS:
        groups.setdefault(spec.group, []).append(spec)

    group_titles = {
        "base": "Base Fields (always required)",
        "conditional": "Conditional Fields",
        "debt": "Debt Security Fields (C.9)",
        "deriv_common": "Derivative Common Fields",
        "option": "Option Fields (C.11.c)",
        "ref_instrument": "Reference Instrument Fields",
        "swap": "Swap Fields (C.11.f)",
        "forward": "Forward/Future Fields",
        "other_deriv": "Other Derivative Fields",
        "liquidity": "Liquidity Classification Fields (C.7)",
    }

    header = f"{'CSV Column':<30} {'Field Name':<30} {'Type':<8} {'Required':<12} {'Description'}"
    sep = "-" * len(header)

    print("N-PORT Holdings Data Schema")
    print("=" * 27)
    print()

    for group_key in group_titles:
        specs = groups.get(group_key, [])
        if not specs:
            continue
        print(f"  {group_titles[group_key]} ({len(specs)} fields)")
        print(f"  {sep}")
        print(f"  {header}")
        print(f"  {sep}")
        for s in specs:
            req = s.required
            if s.condition:
                req = f"{s.required}*"
            print(f"  {s.csv_header:<30} {s.name:<30} {s.value_type:<8} {req:<12} {s.description}")
        print()

    total = len(FIELD_SPECS)
    always = sum(1 for s in FIELD_SPECS if s.required == "always")
    cond = sum(1 for s in FIELD_SPECS if s.required == "conditional")
    optional = sum(1 for s in FIELD_SPECS if s.required == "optional")
    print(f"Total: {total} fields ({always} always, {cond} conditional, {optional} optional)")
