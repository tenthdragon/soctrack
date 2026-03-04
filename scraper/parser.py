"""
Number parser for TikTok metrics.
Handles formats: "1.2M", "45.3K", "890", "1,234", etc.
"""

import re


def parse_metric(text: str) -> int:
    """
    Parse TikTok metric string to integer.

    Examples:
        "1.2M"   → 1200000
        "45.3K"  → 45300
        "890"    → 890
        "1,234"  → 1234
        "12.5k"  → 12500
        ""       → 0
    """
    if not text:
        return 0

    text = text.strip().replace(",", "").replace(" ", "")

    # Handle M (millions)
    match = re.match(r"^([\d.]+)\s*[Mm]$", text)
    if match:
        return int(float(match.group(1)) * 1_000_000)

    # Handle K (thousands)
    match = re.match(r"^([\d.]+)\s*[Kk]$", text)
    if match:
        return int(float(match.group(1)) * 1_000)

    # Handle B (billions)
    match = re.match(r"^([\d.]+)\s*[Bb]$", text)
    if match:
        return int(float(match.group(1)) * 1_000_000_000)

    # Plain number
    match = re.match(r"^[\d.]+$", text)
    if match:
        return int(float(text))

    return 0


def format_metric(value: int) -> str:
    """
    Format integer to human-readable string.

    Examples:
        1200000  → "1.2M"
        45300    → "45.3K"
        890      → "890"
    """
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)
