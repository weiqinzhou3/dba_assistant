from dataclasses import dataclass


@dataclass(frozen=True)
class CoverSpec:
    title: str
    subtitle: str
    metadata_order: tuple[str, ...]


def build_cover_spec(
    title: str,
    subtitle: str,
    metadata_order: tuple[str, ...] = ("client", "environment", "generated_at"),
) -> CoverSpec:
    return CoverSpec(title=title, subtitle=subtitle, metadata_order=metadata_order)
