#!/usr/bin/env python3
"""
Document AI専用テストスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトルートをPATHに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_document_ai():
    """Document AI の基本テスト"""
    
    print("=== Document AI テスト開始 ===")
    
    # 環境変数確認
    print(f"GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")
    print(f"DOCUMENT_AI_PROJECT_ID: {os.getenv('DOCUMENT_AI_PROJECT_ID')}")
    print(f"DOCUMENT_AI_PROCESSOR_ID: {os.getenv('DOCUMENT_AI_PROCESSOR_ID')}")
    print(f"DOCUMENT_AI_LOCATION: {os.getenv('DOCUMENT_AI_LOCATION')}")
    
    # 認証ファイル確認
    credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if credentials_path and os.path.exists(credentials_path):
        print(f"✅ 認証ファイル存在: {credentials_path}")
    else:
        print(f"❌ 認証ファイル不存在: {credentials_path}")
        return False
    
    try:
        # Document AI クライアント作成テスト
        print("\n--- Document AI クライアント作成テスト ---")
        from google.cloud import documentai
        client = documentai.DocumentProcessorServiceClient()
        print("✅ Document AI クライアント作成成功")
        
        # プロセッサー情報取得テスト
        print("\n--- プロセッサー情報取得テスト ---")
        project_id = os.getenv('DOCUMENT_AI_PROJECT_ID')
        processor_id = os.getenv('DOCUMENT_AI_PROCESSOR_ID') 
        location = os.getenv('DOCUMENT_AI_LOCATION')
        
        processor_name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
        print(f"プロセッサー名: {processor_name}")
        
        processor = client.get_processor(name=processor_name)
        print(f"✅ プロセッサー取得成功: {processor.display_name}")
        print(f"   状態: {processor.state.name}")
        print(f"   タイプ: {processor.type_}")
        
        # 実際の画像処理テスト
        print("\n--- 画像処理テスト ---")
        
        # テスト画像を探す
        test_image_paths = [
            "data/output/split_images/test_20250906_095438/page_001_mask1/page_001_mask1_original.jpg",
            "pdf/test.jpg",
            "test.jpg"
        ]
        
        test_image_path = None
        for path in test_image_paths:
            if os.path.exists(path):
                test_image_path = path
                break
        
        if not test_image_path:
            print("⚠️  テスト画像が見つかりません。画像処理テストはスキップ")
            return True
            
        print(f"テスト画像: {test_image_path}")
        
        # 画像読み込み
        with open(test_image_path, "rb") as image_file:
            image_content = image_file.read()
        
        # Document AI リクエスト作成
        raw_document = documentai.RawDocument(
            content=image_content,
            mime_type="image/jpeg"
        )
        
        request = documentai.ProcessRequest(
            name=processor_name,
            raw_document=raw_document
        )
        
        # Document AI実行
        print("Document AI処理実行中...")
        result = client.process_document(request=request)
        
        # 結果確認
        extracted_text = result.document.text
        print(f"✅ Document AI処理成功!")
        print(f"抽出テキスト長: {len(extracted_text)} 文字")
        print(f"抽出テキスト(最初の100文字): {extracted_text[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Document AI エラー: {e}")
        print(f"エラータイプ: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_document_ai()
    if success:
        print("\n🎉 Document AI テスト成功!")
    else:
        print("\n💥 Document AI テスト失敗")
        sys.exit(1)