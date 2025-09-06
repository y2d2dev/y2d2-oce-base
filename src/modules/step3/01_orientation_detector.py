"""
画像の向き検出モジュール
LLMを使用して画像の正しい向きを判定
"""

import os
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrientationDetectionResult:
    """向き検出結果を格納するデータクラス"""
    angle: int = 0  # 回転角度: 0, 90, -90, 180
    confidence: float = 0.0
    llm_response: Optional[Dict] = None
    success: bool = True
    error: Optional[str] = None


class OrientationDetector:
    """画像の向き検出専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): 向き検出設定
        """
        self.config = config.get('orientation_detection', {})
        self.enabled = self.config.get('enabled', True)
        self.use_llm = self.config.get('use_llm', True)
        self.debug_save = self.config.get('debug_save', False)
        self.debug_save_dir = None
        
        # LLM評価器（後で注入）
        self.llm_evaluator = None
        self.prompts = {}
        
        logger.debug(f"OrientationDetector初期化: use_llm={self.use_llm}")
    
    def attach_llm_evaluator(self, llm_evaluator: Any, prompts: Dict):
        """
        LLM評価器とプロンプトをアタッチ
        
        Args:
            llm_evaluator: LLM評価器インスタンス
            prompts (Dict): プロンプト設定
        """
        self.llm_evaluator = llm_evaluator
        self.prompts = prompts
        logger.debug("LLM評価器をアタッチしました")
    
    async def detect(self, image_path: str, add_star: bool = True, 
              temp_dir: Optional[str] = None, use_llm: bool = True) -> OrientationDetectionResult:
        """
        画像の向きを検出
        
        Args:
            image_path (str): 検出対象画像パス
            add_star (bool): デバッグ用の星マーカーを追加
            temp_dir (Optional[str]): 一時ディレクトリ
            use_llm (bool): LLMを使用するか
            
        Returns:
            OrientationDetectionResult: 検出結果
        """
        if not self.enabled:
            logger.debug("向き検出は無効化されています")
            return OrientationDetectionResult(angle=0, success=True)
        
        if not os.path.exists(image_path):
            logger.error(f"画像ファイルが見つかりません: {image_path}")
            return OrientationDetectionResult(
                angle=0, 
                success=False, 
                error=f"画像ファイルが見つかりません: {image_path}"
            )
        
        try:
            # LLMを使用する場合（非同期対応）
            if use_llm and self.use_llm and self.llm_evaluator:
                return await self._detect_with_llm(image_path, add_star, temp_dir)
            else:
                # LLM無しの場合（簡易ヒューリスティック or 固定値）
                return self._detect_without_llm(image_path)
                
        except Exception as e:
            logger.error(f"向き検出エラー: {e}")
            return OrientationDetectionResult(
                angle=0,
                success=False,
                error=str(e)
            )
    
    async def _detect_with_llm(self, image_path: str, add_star: bool, 
                        temp_dir: Optional[str]) -> OrientationDetectionResult:
        """
        LLMを使用した向き検出
        
        Args:
            image_path (str): 検出対象画像パス
            add_star (bool): デバッグ用の星マーカーを追加
            temp_dir (Optional[str]): 一時ディレクトリ
            
        Returns:
            OrientationDetectionResult: 検出結果
        """
        logger.debug(f"LLMによる向き検出開始: {os.path.basename(image_path)}")
        
        try:
            # デバッグ用画像の準備（星マーカー付き）
            marked_image_path = image_path
            if add_star and self.debug_save:
                marked_image_path = self._add_star_marker(image_path, temp_dir)
            
            # プロンプトを取得
            orientation_prompts = self.prompts.get('orientation_judgment', {})
            
            # LLM評価を実行（非同期）
            llm_result = await self.llm_evaluator.evaluate_orientation(
                marked_image_path, 
                orientation_prompts
            )
            
            if not llm_result.get("success"):
                logger.warning(f"LLM評価失敗: {llm_result.get('error')}")
                return OrientationDetectionResult(
                    angle=0,
                    success=False,
                    error=llm_result.get('error'),
                    llm_response=llm_result
                )
            
            # 結果から回転角度を抽出
            judgment = llm_result.get("judgment", {})
            rotation_angle = self._extract_rotation_angle(judgment)
            confidence = judgment.get("confidence_score", 0.5)
            
            logger.debug(f"LLM検出結果: 回転角度={rotation_angle}度, 信頼度={confidence}")
            
            return OrientationDetectionResult(
                angle=rotation_angle,
                confidence=confidence,
                llm_response=llm_result,
                success=True
            )
            
        except Exception as e:
            logger.error(f"LLM向き検出エラー: {e}")
            return OrientationDetectionResult(
                angle=0,
                success=False,
                error=str(e)
            )
    
    def _detect_without_llm(self, image_path: str) -> OrientationDetectionResult:
        """
        LLM無しの向き検出（シンプルなフォールバック）
        
        Args:
            image_path (str): 検出対象画像パス
            
        Returns:
            OrientationDetectionResult: 検出結果
        """
        logger.debug("LLM無しの向き検出（回転なし）")
        
        # 簡易実装：常に0度（回転なし）を返す
        # 将来的には画像解析ベースのヒューリスティックを実装可能
        return OrientationDetectionResult(
            angle=0,
            confidence=1.0,
            success=True
        )
    
    def _add_star_marker(self, image_path: str, temp_dir: Optional[str]) -> str:
        """
        デバッグ用の星マーカーを画像に追加
        
        Args:
            image_path (str): 元画像パス
            temp_dir (Optional[str]): 一時ディレクトリ
            
        Returns:
            str: マーカー付き画像のパス
        """
        try:
            import cv2
            import numpy as np
            
            # 画像を読み込み
            img = cv2.imread(image_path)
            if img is None:
                return image_path
            
            # 星マーカーを左上に追加
            h, w = img.shape[:2]
            marker_size = min(w, h) // 20
            cv2.putText(img, "★", (10, marker_size), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
            
            # 一時ファイルとして保存
            if temp_dir:
                os.makedirs(temp_dir, exist_ok=True)
                base_name = os.path.basename(image_path)
                marked_path = os.path.join(temp_dir, f"marked_{base_name}")
            else:
                base, ext = os.path.splitext(image_path)
                marked_path = f"{base}_marked{ext}"
            
            cv2.imwrite(marked_path, img)
            return marked_path
            
        except Exception as e:
            logger.warning(f"星マーカー追加失敗: {e}")
            return image_path
    
    def _extract_rotation_angle(self, judgment: Dict) -> int:
        """
        LLM判定結果から回転角度を抽出
        
        Args:
            judgment (Dict): LLM判定結果
            
        Returns:
            int: 回転角度（0, 90, -90, 180）
        """
        # 様々な形式の回転角度表現に対応
        rotation = judgment.get("recommended_angle", judgment.get("rotation_angle", 0))
        
        if isinstance(rotation, str):
            rotation = rotation.lower().strip()
            if rotation in ["0", "none", "正しい", "正常"]:
                return 0
            elif rotation in ["90", "右90", "時計回り90"]:
                return 90
            elif rotation in ["-90", "左90", "反時計回り90"]:
                return -90
            elif rotation in ["180", "上下逆", "逆さま"]:
                return 180
            else:
                # 数値を抽出
                try:
                    import re
                    numbers = re.findall(r'-?\d+', rotation)
                    if numbers:
                        angle = int(numbers[0])
                        # 正規化
                        if -45 <= angle <= 45:
                            return 0
                        elif 45 < angle <= 135:
                            return 90
                        elif -135 <= angle < -45:
                            return -90
                        else:
                            return 180
                except:
                    pass
        
        elif isinstance(rotation, (int, float)):
            angle = int(rotation)
            # 正規化
            if -45 <= angle <= 45:
                return 0
            elif 45 < angle <= 135:
                return 90
            elif -135 <= angle < -45:
                return -90
            else:
                return 180
        
        return 0
    
    def _evaluate_with_generic_llm(self, image_path: str, prompts: Dict) -> Dict:
        """
        汎用LLM評価メソッドを使用（フォールバック）
        
        Args:
            image_path (str): 評価対象画像パス
            prompts (Dict): プロンプト設定
            
        Returns:
            Dict: 評価結果
        """
        # 基本的な評価を試みる
        try:
            if hasattr(self.llm_evaluator, 'evaluate'):
                return self.llm_evaluator.evaluate(image_path, prompts)
            else:
                return {
                    "success": False,
                    "error": "LLM評価メソッドが利用できません"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }