"""
The pipeline rules (VS-02 plan A22.3): authored configuration, loaded lazily,
and the methodology digest that identifies everything able to change a figure.

config/intelligence/pipeline_rules.yaml carries:

    pipeline_version   bumped whenever anything that can change a figure
                       changes. It is the key a methodology digest is pinned
                       under, and it is not inside the digest
    closed_stages      the stages a closed deal is expected to be in. A deal
                       is open by is_active alone (plan A8.2); these only say
                       when a deal's stage and activity disagree

Every other parameter is a named constant in code, eight in all. Three are
M1's, in app/fx/convert.py; five are this package's, each defined once, in
the module that holds its rule. None is restated here: the digest is computed
from the constants themselves and from the loaded file, so a changed constant
changes the digest.

The methodology digest's canonical form is frozen by plan A22.3 item 3
(OD-1) and is not a choice made here: a JSON object of nine keys whose every
value is a string or a list of strings, serialised by VS-01's canonical_json,
encoded as UTF-8 and hashed with SHA-256.

Unknown and missing keys are refused, and a broken file is refused naming
the broken key, or the file alone when it cannot be parsed at all. The stage
vocabulary is not redeclared: a closed stage must be a value of the frozen D1
vocabulary. The file names no rate-set version (plan A7.3).

Nothing is read at import or at application startup. default_pipeline_rules()
reads the file on first use and keeps the result for the process. A load that
fails is not kept, so a corrected file loads on the next call.
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, localcontext
from pathlib import Path

import yaml

from app.fx.convert import ARITHMETIC_PRECISION, BASE_QUANTUM, ROUNDING_MODE
from app.intelligence.contract import canonical_json, decimal_text
from app.normalization.config import default_config
from app.pipeline.aggregation import CONCENTRATION_TOP_N, CUMULATIVE_POINTS, PERIOD_HORIZON
from app.pipeline.errors import PipelineConfigError
from app.pipeline.measures import SHARE_QUANTUM, WEIGHT_QUANTUM

DEFAULT_PIPELINE_RULES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "intelligence" / "pipeline_rules.yaml"
)

FORMAT_VERSION = 1

_KEYS = frozenset({"version", "pipeline_version", "closed_stages"})


@dataclass(frozen=True)
class PipelineRules:
    """Complete, validated, immutable pipeline rules."""

    pipeline_version: int
    closed_stages: frozenset[str]

    @property
    def methodology_text(self) -> str:
        """
        The methodology's canonical text (plan A22.3 item 3).

        Nine keys, every value a string or a list of strings. An integer is
        written in base 10; a quantum as VS-01's decimal_text; the closed
        stages as their distinct values ascending; the cumulative points in
        the constant's own order. pipeline_version is not among them.
        """
        return canonical_json({
            "arithmetic_precision": str(ARITHMETIC_PRECISION),
            "base_quantum": _exact_text(BASE_QUANTUM),
            "closed_stages": sorted(self.closed_stages),
            "concentration_top_n": str(CONCENTRATION_TOP_N),
            "cumulative_points": [str(point) for point in CUMULATIVE_POINTS],
            "period_horizon": str(PERIOD_HORIZON),
            "rounding": ROUNDING_MODE,
            "share_quantum": _exact_text(SHARE_QUANTUM),
            "weight_quantum": _exact_text(WEIGHT_QUANTUM),
        })

    @property
    def methodology_digest(self) -> str:
        """The SHA-256 of the canonical text's UTF-8 bytes, as 64 lowercase hex characters."""
        return hashlib.sha256(self.methodology_text.encode("utf-8")).hexdigest()


@functools.lru_cache(maxsize=1)
def default_pipeline_rules() -> PipelineRules:
    """Load (once, on first use) the repository pipeline rules."""
    return load_pipeline_rules(DEFAULT_PIPELINE_RULES_PATH)


def load_pipeline_rules(path: str | Path) -> PipelineRules:
    """Load and validate a pipeline rules file."""
    path = Path(path)
    where = str(path)
    if not path.is_file():
        raise PipelineConfigError(f"Pipeline rules file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, ValueError) as exc:
        # ValueError is what bytes that are not UTF-8 raise: not a yaml.YAMLError.
        raise PipelineConfigError(f"{where}: invalid YAML: {exc}") from exc
    data = _exact_keys(data, where)
    version = data["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != FORMAT_VERSION:
        raise PipelineConfigError(f"{where}: unsupported version {version!r}")
    return PipelineRules(
        pipeline_version=_positive_int(data["pipeline_version"], f"{where}: pipeline_version"),
        closed_stages=_closed_stages(data["closed_stages"], f"{where}: closed_stages"),
    )


def _closed_stages(raw: object, loc: str) -> frozenset[str]:
    """A non-empty list of D1 stage values. A value written twice is one closed stage."""
    if not isinstance(raw, list) or not raw:
        raise PipelineConfigError(f"{loc}: expected a non-empty list of stage values")
    stages = default_config().fields["deals"]["stage"].enum_values
    for index, stage in enumerate(raw):
        if not isinstance(stage, str) or stage not in stages:
            raise PipelineConfigError(f"{loc}[{index}]: {stage!r} is not a Layer 1 stage value")
    return frozenset(raw)


def _exact_keys(data: object, loc: str) -> dict[str, object]:
    """The file's mapping, after checking it has exactly the authored keys."""
    if not isinstance(data, dict):
        raise PipelineConfigError(f"{loc}: expected a mapping")
    missing = sorted(_KEYS - set(map(str, data)))
    unknown = sorted(set(map(str, data)) - _KEYS)
    if missing or unknown:
        raise PipelineConfigError(f"{loc}: missing keys {missing}, unknown keys {unknown}")
    return data


def _positive_int(value: object, loc: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PipelineConfigError(f"{loc}: expected an integer of at least 1")
    return value


def _exact_text(value: Decimal) -> str:
    """
    VS-01's decimal_text of a quantum, whatever Decimal context is in force.

    decimal_text normalizes in the current context, so this states one of
    its own: as many digits as the value holds, and the widest exponents.
    Normalizing is then exact and can raise no signal, so the digest cannot
    depend on the caller's context or on the process default.
    """
    digits = max(1, len(value.as_tuple().digits))
    with localcontext(Context(prec=digits, Emin=MIN_EMIN, Emax=MAX_EMAX)):
        return decimal_text(value)
