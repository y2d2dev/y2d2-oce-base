"""
画像回転処理モジュール
検出された角度に基づいて画像を回転
"""

import os
import logging
from typing import Dict, Optional, List
import cv2

logger = logging.getLogger(__name__)


class ImageRotator:
    """画像回転処理専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): 回転処理設定
        """
        self.config = config.get('orientation_detection', {})
        self.output_suffix = self.config.get('output_suffix', '_rot')
        self.output_format = self.config.get('output_format', '.jpg')
        self.jpeg_quality = self.config.get('jpeg_quality', 95)
        
        logger.debug("ImageRotator初期化完了")
    
    def rotate_image(self, image_path: str, angle: int, 
                    output_path: Optional[str] = None) -> Dict:
        """
        画像を指定角度で回転
        
        Args:
            image_path (str): 入力画像パス
            angle (int): 回転角度（0, 90, -90, 180）
            output_path (Optional[str]): 出力パス（省略時は自動生成）
            
        Returns:
            Dict: 処理結果
        """
        logger.debug(f"画像回転処理: {os.path.basename(image_path)}, 角度={angle}度")
        
        try:
            # 角度が0の場合は何もしない
            if angle == 0:
                return {
                    "success": True,
                    "rotated": False,
                    "angle": 0,
                    "input_path": image_path,
                    "output_path": image_path,
                    "message": "回転不要"
                }
            
            # 画像を読み込み
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"画像読み込み失敗: {image_path}")
                return {
                    "success": False,
                    "error": f"画像読み込み失敗: {image_path}",
                    "input_path": image_path
                }
            
            # 回転処理
            rotated_img = self._apply_rotation(img, angle)
            
            # 出力パスを生成
            if output_path is None:
                output_path = self._generate_output_path(image_path, angle)
            
            # 保存
            success = self._save_image(rotated_img, output_path)
            
            if success:
                logger.debug(f"回転画像保存: {output_path}")
                return {
                    "success": True,
                    "rotated": True,
                    "angle": angle,
                    "input_path": image_path,
                    "output_path": output_path,
                    "message": f"{angle}度回転完了"
                }
            else:
                return {
                    "success": False,
                    "error": "画像保存失敗",
                    "input_path": image_path
                }
                
        except Exception as e:
            logger.error(f"画像回転エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "input_path": image_path
            }
    
    def _apply_rotation(self, img, angle: int):
        """
        OpenCVを使用して画像を回転
        
        Args:
            img: OpenCV画像オブジェクト
            angle (int): 回転角度
            
        Returns:
            回転後の画像
        """
        if angle == 90:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif angle == -90:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif angle in (180, -180):
            return cv2.rotate(img, cv2.ROTATE_180)
        else:
            # 任意角度の回転（将来的な拡張用）
            height, width = img.shape[:2]
            center = (width // 2, height // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            
            # 回転後の画像サイズを計算
            cos = abs(rotation_matrix[0, 0])
            sin = abs(rotation_matrix[0, 1])
            new_width = int(height * sin + width * cos)
            new_height = int(height * cos + width * sin)
            
            # 回転行列を調整
            rotation_matrix[0, 2] += (new_width - width) / 2
            rotation_matrix[1, 2] += (new_height - height) / 2
            
            return cv2.warpAffine(img, rotation_matrix, (new_width, new_height),
                                 borderMode=cv2.BORDER_CONSTANT,
                                 borderValue=(255, 255, 255))
    
    def _generate_output_path(self, input_path: str, angle: int) -> str:
        """
        出力パスを自動生成
        
        Args:
            input_path (str): 入力画像パス
            angle (int): 回転角度
            
        Returns:
            str: 出力パス
        """
        base, ext = os.path.splitext(input_path)
        # 既存の回転サフィックスを削除
        if self.output_suffix in base:
            base = base.replace(self.output_suffix, '')
        
        # 新しいサフィックスを追加
        if angle != 0:
            output_path = f"{base}{self.output_suffix}{ext or self.output_format}"
        else:
            output_path = f"{base}{ext or self.output_format}"
        
        return output_path
    
    def _save_image(self, img, output_path: str) -> bool:
        """
        画像を保存
        
        Args:
            img: 保存する画像
            output_path (str): 出力パス
            
        Returns:
            bool: 成功時True
        """
        try:
            # ディレクトリを作成
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # JPEG品質パラメータ
            if output_path.lower().endswith(('.jpg', '.jpeg')):
                params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            else:
                params = []
            
            return cv2.imwrite(output_path, img, params)
            
        except Exception as e:
            logger.error(f"画像保存エラー: {e}")
            return False
    
    def batch_rotate(self, image_paths: List[str], angles: List[int],
                    output_dir: Optional[str] = None) -> List[Dict]:
        """
        複数画像の一括回転処理
        
        Args:
            image_paths (List[str]): 入力画像パスリスト
            angles (List[int]): 各画像の回転角度リスト
            output_dir (Optional[str]): 出力ディレクトリ
            
        Returns:
            List[Dict]: 各画像の処理結果リスト
        """
        results = []
        
        if len(image_paths) != len(angles):
            logger.error("画像数と角度数が一致しません")
            return []
        
        for image_path, angle in zip(image_paths, angles):
            if output_dir:
                base_name = os.path.basename(image_path)
                output_path = os.path.join(output_dir, base_name)
            else:
                output_path = None
            
            result = self.rotate_image(image_path, angle, output_path)
            results.append(result)
        
        return results
    
    def get_rotation_stats(self, results: List[Dict]) -> Dict:
        """
        回転処理の統計情報を生成
        
        Args:
            results (List[Dict]): 処理結果リスト
            
        Returns:
            Dict: 統計情報
        """
        if not results:
            return {
                "total": 0,
                "rotated": 0,
                "skipped": 0,
                "failed": 0
            }
        
        total = len(results)
        rotated = len([r for r in results if r.get("rotated")])
        skipped = len([r for r in results if r.get("success") and not r.get("rotated")])
        failed = len([r for r in results if not r.get("success")])
        
        angle_distribution = {}
        for result in results:
            if result.get("success"):
                angle = result.get("angle", 0)
                angle_distribution[angle] = angle_distribution.get(angle, 0) + 1
        
        return {
            "total": total,
            "rotated": rotated,
            "skipped": skipped,
            "failed": failed,
            "rotation_rate": rotated / total if total > 0 else 0.0,
            "angle_distribution": angle_distribution
        }