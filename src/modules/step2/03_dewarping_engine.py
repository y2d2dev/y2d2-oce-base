"""
歪み補正エンジンモジュール
YOLOを使用した文書歪み補正処理
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DewarpingEngine:
    """歪み補正処理専用クラス"""
    
    def __init__(self, config: Dict):
        """
        Args:
            config (Dict): 歪み補正設定
        """
        self.config = config.get('dewarping', {})
        self.yolo_model_path = self.config.get('yolo_model_path')
        self.confidence_threshold = self.config.get('confidence_threshold', 0.6)
        self.num_grid_lines = self.config.get('num_grid_lines', 12)
        self.polynomial_degree = self.config.get('polynomial_degree', 4)
        self.num_point_percent = self.config.get('num_point_percent', 0.2)
        self.threshold_coefficient = self.config.get('threshold_coefficient', 0.03)
        self.enable_strong_correction = self.config.get('enable_strong_correction', True)
        self.yolo_device = self.config.get('yolo_device', 'cpu')
        self.crop_margin_px = self.config.get('crop_margin_px', 0)
        self.mask_dilation_px = self.config.get('mask_dilation_px', 15)
        
        self.yolo_model = None
        
        logger.debug(f"DewarpingEngine初期化: YOLO={self.yolo_model_path}, device={self.yolo_device}")
    
    def _load_yolo_model(self):
        """YOLOモデルをロード"""
        if self.yolo_model is not None:
            return True
            
        try:
            if not self.yolo_model_path or not os.path.exists(self.yolo_model_path):
                logger.warning(f"YOLOモデルが見つかりません: {self.yolo_model_path}")
                return False
            
            # YOLOv8をロード
            import ultralytics
            self.yolo_model = ultralytics.YOLO(self.yolo_model_path)
            self.yolo_model.to(self.yolo_device)
            
            logger.debug(f"YOLOモデルロード完了: {self.yolo_device}")
            return True
            
        except ImportError:
            logger.error("ultralytics（YOLOv8）がインストールされていません")
            return False
        except Exception as e:
            logger.error(f"YOLOモデルロードエラー: {e}")
            return False
    
    def _detect_document_corners(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        YOLOを使用して文書の四隅を検出
        
        Args:
            image (np.ndarray): 入力画像
            
        Returns:
            Optional[np.ndarray]: 四隅の座標 [4x2] or None
        """
        try:
            if not self._load_yolo_model():
                return None
            
            # YOLO推論
            results = self.yolo_model.predict(
                image,
                conf=self.confidence_threshold,
                verbose=False
            )
            
            if not results or len(results) == 0:
                return None
            
            result = results[0]
            
            # 最も信頼度の高い検出結果を取得
            if result.boxes is not None and len(result.boxes) > 0:
                # バウンディングボックスから四隅を推定
                box = result.boxes[0].xyxy[0].cpu().numpy()  # [x1, y1, x2, y2]
                
                corners = np.array([
                    [box[0], box[1]],  # 左上
                    [box[2], box[1]],  # 右上
                    [box[2], box[3]],  # 右下
                    [box[0], box[3]]   # 左下
                ], dtype=np.float32)
                
                return corners
            
            return None
            
        except Exception as e:
            logger.error(f"文書検出エラー: {e}")
            return None
    
    def _create_dewarp_grid(self, image_shape: Tuple[int, int], corners: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        歪み補正用のグリッドを作成
        
        Args:
            image_shape (Tuple[int, int]): 画像サイズ (height, width)
            corners (np.ndarray): 文書の四隅座標
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (map_x, map_y)
        """
        height, width = image_shape
        
        # 目標となる矩形の四隅を定義
        dst_corners = np.array([
            [0, 0],
            [width - 1, 0],
            [width - 1, height - 1],
            [0, height - 1]
        ], dtype=np.float32)
        
        # 透視変換行列を計算
        transform_matrix = cv2.getPerspectiveTransform(corners, dst_corners)
        
        # グリッドマップを作成
        map_x, map_y = np.meshgrid(np.arange(width), np.arange(height))
        map_x = map_x.astype(np.float32)
        map_y = map_y.astype(np.float32)
        
        # 多項式歪み補正（オプション）
        if self.enable_strong_correction:
            map_x, map_y = self._apply_polynomial_correction(map_x, map_y, corners, image_shape)
        
        return map_x, map_y
    
    def _apply_polynomial_correction(self, map_x: np.ndarray, map_y: np.ndarray, 
                                   corners: np.ndarray, image_shape: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
        """
        多項式による細かい歪み補正
        
        Args:
            map_x, map_y (np.ndarray): 基本的な変換マップ
            corners (np.ndarray): 文書の四隅
            image_shape (Tuple[int, int]): 画像サイズ
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: 補正されたマップ
        """
        height, width = image_shape
        
        try:
            # 文書の上辺と下辺から曲線を検出
            top_curve = self._detect_curve(corners[0], corners[1], self.num_grid_lines)
            bottom_curve = self._detect_curve(corners[3], corners[2], self.num_grid_lines)
            
            # 多項式フィッティング
            y_coords = np.linspace(0, height - 1, height)
            
            for i in range(width):
                x_ratio = i / (width - 1)
                
                # 上辺と下辺の曲線から補間
                top_offset = self._interpolate_curve_offset(top_curve, x_ratio)
                bottom_offset = self._interpolate_curve_offset(bottom_curve, x_ratio)
                
                # Y方向の補正を適用
                for j in range(height):
                    y_ratio = j / (height - 1)
                    offset = top_offset * (1 - y_ratio) + bottom_offset * y_ratio
                    map_y[j, i] += offset * self.threshold_coefficient
            
        except Exception as e:
            logger.debug(f"多項式補正スキップ: {e}")
        
        return map_x, map_y
    
    def _detect_curve(self, start_point: np.ndarray, end_point: np.ndarray, num_points: int) -> np.ndarray:
        """
        線分の曲線を検出
        
        Args:
            start_point, end_point (np.ndarray): 始点と終点
            num_points (int): サンプリングポイント数
            
        Returns:
            np.ndarray: 曲線上の点群
        """
        # 簡単な線形補間（実際の実装では画像解析による曲線検出）
        points = np.linspace(start_point, end_point, num_points)
        return points
    
    def _interpolate_curve_offset(self, curve_points: np.ndarray, ratio: float) -> float:
        """
        曲線からのオフセットを補間計算
        
        Args:
            curve_points (np.ndarray): 曲線上の点群
            ratio (float): 補間比率 (0.0-1.0)
            
        Returns:
            float: オフセット値
        """
        if len(curve_points) < 2:
            return 0.0
        
        # 線形補間
        index = ratio * (len(curve_points) - 1)
        idx_low = int(np.floor(index))
        idx_high = int(np.ceil(index))
        
        if idx_low == idx_high:
            return 0.0
        
        weight = index - idx_low
        offset_low = curve_points[idx_low][1] - (curve_points[idx_low][1] * ratio)
        offset_high = curve_points[idx_high][1] - (curve_points[idx_high][1] * ratio)
        
        return offset_low * (1 - weight) + offset_high * weight
    
    def can_process(self, judgment_result: Dict) -> bool:
        """
        歪み補正が必要かどうかを判定
        
        Args:
            judgment_result (Dict): LLM判定結果
            
        Returns:
            bool: 処理が必要な場合True
        """
        if not judgment_result.get("success"):
            return False
        
        judgment = judgment_result.get("judgment", {})
        needs_dewarping = judgment.get("needs_dewarping", False)
        
        return needs_dewarping
    
    def process_image(self, image_path: str, output_path: str) -> Dict:
        """
        画像の歪み補正を実行
        
        Args:
            image_path (str): 入力画像パス
            output_path (str): 出力画像パス
            
        Returns:
            Dict: 処理結果
        """
        logger.debug(f"歪み補正開始: {os.path.basename(image_path)}")
        
        try:
            # 画像読み込み
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "error": f"入力画像が見つかりません: {image_path}"
                }
            
            image = cv2.imread(image_path)
            if image is None:
                return {
                    "success": False,
                    "error": "画像読み込み失敗"
                }
            
            original_height, original_width = image.shape[:2]
            
            # YOLOモデルで文書検出
            corners = self._detect_document_corners(image)
            if corners is None:
                logger.debug("文書検出失敗 - 元画像をそのまま出力")
                
                # 出力ディレクトリ作成
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # 元画像をコピー
                import shutil
                shutil.copy2(image_path, output_path)
                
                return {
                    "success": True,
                    "skipped": True,
                    "reason": "文書検出失敗",
                    "output_paths": [output_path],
                    "original_size": [original_width, original_height],
                    "processed_size": [original_width, original_height]
                }
            
            # 歪み補正グリッド作成
            map_x, map_y = self._create_dewarp_grid(image.shape[:2], corners)
            
            # リマッピング実行
            dewarped_image = cv2.remap(
                image, map_x, map_y, 
                cv2.INTER_LINEAR, 
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255)
            )
            
            # クロップ処理
            if self.crop_margin_px > 0:
                h, w = dewarped_image.shape[:2]
                margin = self.crop_margin_px
                dewarped_image = dewarped_image[
                    margin:h-margin, 
                    margin:w-margin
                ]
            
            # 出力ディレクトリ作成
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 画像保存
            success = cv2.imwrite(output_path, dewarped_image)
            if not success:
                return {
                    "success": False,
                    "error": "画像保存失敗"
                }
            
            processed_height, processed_width = dewarped_image.shape[:2]
            
            logger.debug(f"歪み補正完了: {original_width}x{original_height} → {processed_width}x{processed_height}")
            
            return {
                "success": True,
                "skipped": False,
                "output_paths": [output_path],
                "original_size": [original_width, original_height],
                "processed_size": [processed_width, processed_height],
                "corners_detected": corners.tolist(),
                "file_size_bytes": os.path.getsize(output_path)
            }
            
        except Exception as e:
            logger.error(f"歪み補正エラー: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def batch_process_images(self, page_judgments: List[Dict], output_dir: str) -> Dict:
        """
        複数画像の一括歪み補正処理
        
        Args:
            page_judgments (List[Dict]): ページ判定結果リスト
            output_dir (str): 出力ディレクトリ
            
        Returns:
            Dict: 一括処理結果
        """
        logger.debug("一括歪み補正処理開始")
        
        try:
            processed_count = 0
            results = []
            
            for page_judgment in page_judgments:
                page_number = page_judgment.get("page_number")
                
                # 歪み補正が必要かチェック
                if self.can_process(page_judgment.get("llm_result", {})):
                    logger.debug(f"ページ {page_number}: 歪み補正対象")
                    
                    # 入力画像パスを取得
                    if page_judgment.get("reprocessed_at_scale"):
                        # 再画像化された画像を使用
                        input_path = page_judgment.get("processed_image")
                    else:
                        # 元画像を使用
                        input_path = page_judgment.get("processed_image")
                    
                    if not input_path:
                        continue
                    
                    # 出力パス生成
                    base_name = Path(input_path).stem
                    output_filename = f"{base_name}_dewarped.jpg"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    # 歪み補正実行
                    dewarp_result = self.process_image(input_path, output_path)
                    results.append(dewarp_result)
                    
                    if dewarp_result.get("success"):
                        processed_count += 1
                        # ページ判定データに結果を追加
                        page_judgment["dewarping_applied"] = True
                        page_judgment["dewarped_image"] = output_path
                        page_judgment["processed_images"] = dewarp_result["output_paths"]
                        page_judgment["dewarping_result"] = dewarp_result
                    else:
                        page_judgment["dewarping_applied"] = False
                        page_judgment["dewarping_result"] = dewarp_result
                        logger.warning(f"ページ {page_number} 歪み補正失敗: {dewarp_result.get('error')}")
                else:
                    # 歪み補正不要
                    page_judgment["dewarping_applied"] = False
                    logger.debug(f"ページ {page_number}: 歪み補正不要")
            
            return {
                "success": True,
                "total_processed": len(results),
                "successful_dewarping": processed_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"一括歪み補正エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def get_processing_stats(self, results: List[Dict]) -> Dict:
        """
        歪み補正処理の統計情報を生成
        
        Args:
            results (List[Dict]): 処理結果リスト
            
        Returns:
            Dict: 統計情報
        """
        if not results:
            return {"total": 0, "successful": 0, "failed": 0, "skipped": 0}
        
        successful = len([r for r in results if r.get("success") and not r.get("skipped")])
        skipped = len([r for r in results if r.get("success") and r.get("skipped")])
        failed = len(results) - successful - skipped
        
        return {
            "total": len(results),
            "successful": successful,
            "skipped": skipped,
            "failed": failed,
            "success_rate": successful / len(results) if results else 0.0,
            "skip_rate": skipped / len(results) if results else 0.0
        }
    
    def validate_dewarped_image(self, image_path: str) -> Dict:
        """
        歪み補正された画像の有効性を検証
        
        Args:
            image_path (str): 検証対象画像パス
            
        Returns:
            Dict: 検証結果
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "valid": False,
                    "error": "画像ファイルが存在しません"
                }
            
            # ファイルサイズチェック
            file_size = os.path.getsize(image_path)
            if file_size < 1000:  # 1KB未満は異常
                return {
                    "valid": False,
                    "error": f"ファイルサイズが小さすぎます: {file_size} bytes"
                }
            
            # OpenCVで画像検証
            image = cv2.imread(image_path)
            if image is None:
                return {
                    "valid": False,
                    "error": "画像読み込み失敗"
                }
            
            height, width = image.shape[:2]
            if width < 100 or height < 100:
                return {
                    "valid": False,
                    "error": f"画像サイズが小さすぎます: {width}x{height}"
                }
            
            return {
                "valid": True,
                "image_size": [width, height],
                "file_size_bytes": file_size,
                "format": "JPEG"
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }