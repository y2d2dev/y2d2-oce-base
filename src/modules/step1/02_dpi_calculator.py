"""
DPI計算ロジックモジュール
ページサイズに基づく最適DPI計算を担当
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class DPICalculator:
    """DPI計算専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): PDF処理設定
        """
        self.target_size = config.get('target_size', [2048, 2560])  # [width, height]
        self.min_dpi = config.get('min_dpi', 50)
        self.max_dpi = config.get('max_dpi', 600)
        self.default_dpi = config.get('default_dpi', 300)
        
        logger.debug(f"DPICalculator初期化: target_size={self.target_size}, DPI範囲={self.min_dpi}-{self.max_dpi}")
    
    def calculate_optimal_dpi(self, page_width: float, page_height: float) -> int:
        """
        ページサイズに基づいて最適なDPIを計算
        
        Args:
            page_width (float): ページ幅（ポイント単位）
            page_height (float): ページ高さ（ポイント単位）
            
        Returns:
            int: 最適なDPI値
        """
        if page_width <= 0 or page_height <= 0:
            logger.warning(f"無効なページサイズ: {page_width}x{page_height}, デフォルトDPIを使用")
            return self.default_dpi
        
        target_width, target_height = self.target_size
        
        # ポイントからピクセルへの変換（72ポイント=1インチ）
        width_dpi = (target_width * 72) / page_width
        height_dpi = (target_height * 72) / page_height
        
        # より制限の厳しい（小さい）DPIを選択（アスペクト比を維持）
        optimal_dpi = min(width_dpi, height_dpi)
        
        # DPI範囲内にクランプ
        optimal_dpi = max(self.min_dpi, min(self.max_dpi, optimal_dpi))
        
        # 整数に丸める
        calculated_dpi = int(optimal_dpi)
        
        logger.debug(f"DPI計算: ページサイズ{page_width:.1f}x{page_height:.1f}pt → {calculated_dpi}DPI")
        
        return calculated_dpi
    
    def calculate_output_size(self, page_width: float, page_height: float, dpi: int) -> Tuple[int, int]:
        """
        指定されたDPIでの出力画像サイズを計算
        
        Args:
            page_width (float): ページ幅（ポイント単位）
            page_height (float): ページ高さ（ポイント単位）
            dpi (int): DPI値
            
        Returns:
            Tuple[int, int]: (width, height) 出力画像サイズ（ピクセル）
        """
        # ポイントからピクセルへの変換
        width_px = int((page_width * dpi) / 72.0)
        height_px = int((page_height * dpi) / 72.0)
        
        return (width_px, height_px)
    
    def get_zoom_factor(self, dpi: int) -> float:
        """
        指定されたDPIに対応するズーム倍率を計算
        
        Args:
            dpi (int): DPI値
            
        Returns:
            float: ズーム倍率（72 DPIがベース）
        """
        return dpi / 72.0
    
    def validate_dpi(self, dpi: int) -> Dict:
        """
        DPI値の有効性を検証
        
        Args:
            dpi (int): 検証対象のDPI値
            
        Returns:
            Dict: 検証結果
        """
        if dpi < self.min_dpi:
            return {
                "valid": False,
                "error": f"DPI値が最小値より小さいです: {dpi} < {self.min_dpi}",
                "suggested_dpi": self.min_dpi
            }
        
        if dpi > self.max_dpi:
            return {
                "valid": False,
                "error": f"DPI値が最大値より大きいです: {dpi} > {self.max_dpi}",
                "suggested_dpi": self.max_dpi
            }
        
        return {
            "valid": True,
            "dpi": dpi
        }
    
    def get_dpi_info(self, page_width: float, page_height: float) -> Dict:
        """
        指定されたページサイズに対するDPI情報を取得
        
        Args:
            page_width (float): ページ幅（ポイント単位）
            page_height (float): ページ高さ（ポイント単位）
            
        Returns:
            Dict: DPI情報
        """
        optimal_dpi = self.calculate_optimal_dpi(page_width, page_height)
        output_size = self.calculate_output_size(page_width, page_height, optimal_dpi)
        zoom_factor = self.get_zoom_factor(optimal_dpi)
        
        # 各DPIレベルでのサイズ情報
        dpi_levels = {
            "min": self.min_dpi,
            "optimal": optimal_dpi,
            "default": self.default_dpi,
            "max": self.max_dpi
        }
        
        size_info = {}
        for level, dpi in dpi_levels.items():
            size = self.calculate_output_size(page_width, page_height, dpi)
            size_info[level] = {
                "dpi": dpi,
                "output_size": size,
                "zoom_factor": self.get_zoom_factor(dpi)
            }
        
        return {
            "page_size_pt": [page_width, page_height],
            "target_size_px": self.target_size,
            "recommended": {
                "dpi": optimal_dpi,
                "output_size": output_size,
                "zoom_factor": zoom_factor
            },
            "dpi_levels": size_info,
            "constraints": {
                "min_dpi": self.min_dpi,
                "max_dpi": self.max_dpi,
                "default_dpi": self.default_dpi
            }
        }
    
    def adjust_dpi_for_memory(self, dpi: int, max_pixels: int = 10000000) -> int:
        """
        メモリ制限に基づいてDPIを調整
        
        Args:
            dpi (int): 元のDPI値
            max_pixels (int): 最大ピクセル数（デフォルト10M）
            
        Returns:
            int: 調整されたDPI値
        """
        # 概算でのメモリ使用量チェック（RGB画像として計算）
        estimated_pixels = (dpi ** 2) * 8.5  # A4サイズの概算
        
        if estimated_pixels <= max_pixels:
            return dpi
        
        # 制限内に収まるDPIを計算
        safe_dpi = int((max_pixels / 8.5) ** 0.5)
        adjusted_dpi = max(self.min_dpi, min(safe_dpi, self.max_dpi))
        
        if adjusted_dpi != dpi:
            logger.info(f"メモリ制限によりDPIを調整: {dpi} → {adjusted_dpi}")
        
        return adjusted_dpi