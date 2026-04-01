RISK_LEVEL_STYLES = {
    "normal": {"label": "Normal", "color": "2E7D32"},
    "warning": {"label": "Warning", "color": "ED6C02"},
    "critical": {"label": "Critical", "color": "D32F2F"},
    "urgent": {"label": "Urgent", "color": "6A1B9A"},
}


def get_risk_style(level: str) -> dict[str, str]:
    key = level.strip().lower()
    return RISK_LEVEL_STYLES[key]
