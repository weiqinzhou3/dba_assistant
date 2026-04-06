from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    path = Path(relative_path)
    spec = spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_risk_level_styles_expose_critical_style() -> None:
    module = load_module(
        "templates/reports/shared/risk_level_styles.py",
        "risk_level_styles",
    )

    assert module.RISK_LEVEL_STYLES["critical"]["label"] == "Critical"


def test_rdb_template_spec_exposes_cover_and_disclaimer_flags() -> None:
    module = load_module(
        "templates/reports/rdb-analysis/template_spec.py",
        "rdb_template_spec",
    )

    assert module.TEMPLATE["template_name"] == "rdb-analysis"
    assert module.TEMPLATE["include_disclaimer"] is True
    assert module.TEMPLATE_TEXT["zh-CN"]["cover_title"] == "Redis RDB 分析报告"
    assert module.TEMPLATE_TEXT["en-US"]["summary_heading"] == "Executive Summary"


def test_inspection_template_spec_exposes_summary_heading() -> None:
    module = load_module(
        "templates/reports/inspection/template_spec.py",
        "inspection_template_spec",
    )

    assert module.TEMPLATE["template_name"] == "inspection"
    assert module.TEMPLATE["summary_heading"] == "Executive Summary"
