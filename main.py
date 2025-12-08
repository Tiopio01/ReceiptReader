import os
import sys
import logging
import excel_exporter

# Disable PaddleOCR debug logs to keep the console output clean
logging.getLogger("ppocr").setLevel(logging.ERROR)

def main():
    # --- 1. CONFIGURATION & PATH SETUP ---
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Relative paths to model artifacts (ONNX files)
    # These models must be present in the 'model_local_onnx' and 'det_model_onnx' folders.
    REC_MODEL_DIR = os.path.join(BASE_DIR, 'model_local_onnx', 'inference.onnx') # Path to Recognition Model (ONNX)
    DET_MODEL_DIR = os.path.join(BASE_DIR, 'det_model_onnx', 'inference.onnx')   # Path to Detection Model (ONNX)
    IMG_DIR = os.path.join(BASE_DIR, 'images_to_read')
    
    # Path to the PaddleOCR repository to locate the character dictionary.
    # This assumes a specific directory structure where PaddleOCR is a sibling folder.
    PADDLE_REPO = os.path.abspath(os.path.join(BASE_DIR, '..', 'PaddleOCR_FineTune', 'PaddleOCR'))
    DICT_PATH = os.path.join(PADDLE_REPO, 'ppocr', 'utils', 'en_dict.txt')

    # Verify that critical files exist before starting
    if not os.path.exists(REC_MODEL_DIR):
        print(f"❌ Error: REC Model folder not found: {REC_MODEL_DIR}")
        return
    if not os.path.exists(DICT_PATH):
        print(f"❌ Error: Dictionary not found: {DICT_PATH}")
        return

    print("⏳ Loading models into RAM... (this may take a few seconds)")

    try:
        # Import PaddleOCR. If this fails, the environment is likely missing the package.
        from paddleocr import PaddleOCR
    except ImportError:
        print("\n❌ CRITICAL ERROR: 'paddleocr' library not found.")
        print("💡 TIP: Are you using the correct python environment?")
        print("   If on WSL, ensure you activated the venv:")
        print("   source ../PaddleOCR_FineTune/venv/bin/activate")
        return

    # --- 2. INITIALIZE OCR ENGINE (Singleton) ---
    # We load the models once into memory to avoid reloading for every image.
    # We use parameters optimized for CPU inference with ONNX.
    ocr_engine = PaddleOCR(
        det_model_dir=DET_MODEL_DIR,   # Use local ONNX detection model
        rec_model_dir=REC_MODEL_DIR,   # Use local ONNX recognition model
        rec_char_dict_path=DICT_PATH,  # Character dictionary path
        use_angle_cls=False,           # Disable angle classifier (speed optimization)
        lang='en',                     # Set language to English (prevents downloading Chinese models)
        use_onnx=True,                 # <--- FORCE ONNX RUNTIME
        device='cpu',                  # Use CPU (ONNX Runtime handles providers)
        enable_mkldnn=True             # Enable MKLDNN acceleration for CPU
    )

    print("✅ Models loaded! Ready to scan.")

    # --- 3. BATCH SCANNING LOOP ---
    # Ensure input directory exists
    if not os.path.exists(IMG_DIR):
        os.makedirs(IMG_DIR)
        print(f"📁 Created folder: {IMG_DIR}")

    supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
    # List only files with supported extensions
    files = sorted([f for f in os.listdir(IMG_DIR) if f.lower().endswith(supported_extensions)])

    if not files:
        print(f"⚠️  No images found in: {IMG_DIR}")
        print("   Copy receipt images into this folder and restart the script.")
        return

    print(f"📂 Found {len(files)} images. Starting processing...")

    # --- INIT LOG FILE ---
    RAW_LOG_FILE = "ocr_raw_data.txt"
    with open(RAW_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("=== OCR RAW DATA LOG ===\n")
    print(f"📝 Log file created: {RAW_LOG_FILE}")

    all_extracted_data = []

    for i, filename in enumerate(files, 1):
        print("\n" + "-"*40)
        image_path = os.path.join(IMG_DIR, filename)

        print(f"🚀 Processing {filename} ({i}/{len(files)})...")

        try:
            # Perform inference. This is fast as models are pre-loaded.
            # 'result' usually contains a list of lines, where each line has [coordinates, [text, confidence]]
            result = ocr_engine.ocr(image_path, cls=False)

            # --- COMPATIBILITY LAYER ---
            # Different versions of PaddleOCR (v2 vs v3 / PaddleX) return data in slightly different formats.
            # The following block normalizes the output to a standard list of lines.
            
            # Check if result is a list of objects/dicts (typical in newer versions)
            if isinstance(result, list) and len(result) > 0:
                first_item = result[0]
                # If it's a dictionary-like object (OCRResult)
                if hasattr(first_item, 'keys') or isinstance(first_item, dict):
                    keys = getattr(first_item, 'keys', lambda: first_item.keys())()
                    if 'dt_polys' in keys and 'rec_texts' in keys and 'rec_scores' in keys:
                        # Extract and zip separate arrays into (box, text, score) tuples
                        boxes = first_item['dt_polys']
                        texts = first_item['rec_texts']
                        scores = first_item['rec_scores']
                        
                        lines = []
                        for box, text, score in zip(boxes, texts, scores):
                            lines.append([box, (text, score)])
                        
                        result = [lines]
                
                # Fallback: if predict returns a flat list of lines (older versions)
                elif isinstance(first_item, list) and len(first_item) > 0:
                     # If the first element is a number (coordinate), then the list itself is a single line info
                     # We wrap it in a list to match the expected structure [[line1, line2, ...]]
                     try:
                        if isinstance(first_item[0][0], (int, float)):
                             result = [result]
                     except:
                        pass

            print("\n" + "="*30)
            print(f"    RESULT: {filename}       ")
            print("="*30)

            # Process the normalized result
            if result and result[0]:
                extracted_lines = []
                for line in result[0]:
                    # Standard line format: [ [x,y...], ('text', confidence) ]
                    box = line[0]
                    text_content = line[1][0]
                    confidence = line[1][1]
                    
                    # Print text to console
                    print(f"{text_content}")
                    extracted_lines.append(text_content)

                # --- SAVE RAW TEXT TO LOG ---
                try:
                    with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
                        f.write(f"\n--- START {filename} ---\n")
                        for line in extracted_lines:
                            f.write(f"{line}\n")
                        f.write(f"--- END {filename} ---\n")
                except Exception as e:
                    print(f"⚠️ Error writing log: {e}")

                # --- DATA EXTRACTION & SAVING ---
                print("\n🔍 Extracting key information...")
                # Use heuristics to find Vendor, Total, Date, etc.
                data = excel_exporter.extract_info(extracted_lines, filename)
                print(f"   Data found: {data}")
                
                all_extracted_data.append(data)
            else:
                print("(No text detected)")

        except Exception as e:
            print(f"❌ Error during processing: {e}")

    # --- FINAL SAVING ---
    print("\n" + "="*40)
    print("💾 Saving cumulative Excel report...")
    excel_exporter.save_all_to_excel(all_extracted_data)

if __name__ == "__main__":
    main()