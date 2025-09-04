"""
型変換ユーティリティモジュール
LLM出力の型解釈ユーティリティを提供
"""

from typing import Optional


def to_bool(v) -> bool:
    """
    任意の値をブール値に変換
    
    Args:
        v: 変換対象の値
        
    Returns:
        bool: 変換されたブール値
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true"):
            return True
        if s in ("false"):
            return False
    return False


def to_int(v, default: Optional[int] = None) -> Optional[int]:
    """
    任意の値を整数に変換
    
    Args:
        v: 変換対象の値
        default: 変換失敗時のデフォルト値
        
    Returns:
        Optional[int]: 変換された整数値またはデフォルト値
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    try:
        if isinstance(v, float):
            return int(v)
        s = str(v).strip()
        if s == "":
            return default
        return int(float(s))
    except Exception:
        return default


def to_float(v, default: Optional[float] = None) -> Optional[float]:
    """
    任意の値を浮動小数点数に変換
    
    Args:
        v: 変換対象の値
        default: 変換失敗時のデフォルト値
        
    Returns:
        Optional[float]: 変換された浮動小数点数値またはデフォルト値
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        s = str(v).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default