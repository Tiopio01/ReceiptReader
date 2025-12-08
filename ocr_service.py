import os
import logging
import excel_exporter

# Disable Paddle debug logs
logging.getLogger("ppocr").setLevel(logging.ERROR)

class ReceiptScanner:
    """
    A service class to handle the initialization of the OCR model and scanning of receipt images.
    It encapsulates the dependency on PaddleOCR and manages the model lifecycle.
    """
    def __init__(self):
        self.ocr_engine = None
        self.is_loaded = False
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Paths to local ONNX models for detection and recognition
        self.rec_model_dir = os.path.join(self.base_dir, 'model_local_onnx', 'inference.onnx')
        self.det_model_dir = os.path.join(self.base_dir, 'det_model_onnx', 'inference.onnx')
        
        # Path to the PaddleOCR repository (assumed to be a sibling directory 'PaddleOCR_FineTune/PaddleOCR')
        # This is needed to access the character dictionary ('en_dict.txt')
        self.paddle_repo = os.path.abspath(os.path.join(self.base_dir, '..', 'PaddleOCR_FineTune', 'PaddleOCR'))
        self.dict_path = os.path.join(self.paddle_repo, 'ppocr', 'utils', 'en_dict.txt')
        
    def load_model(self):
        """
        Loads the PaddleOCR model into memory.
        This operation is resource-intensive and should be called once.
        Returns:
            (bool, str): A tuple containing success status and a message.
        """
        if self.is_loaded:
            return True, "Model already loaded"

        if not os.path.exists(self.rec_model_dir):
            return False, f"REC Model not found: {self.rec_model_dir}"
        if not os.path.exists(self.dict_path):
             # Fail if dictionary is missing, as it's crucial for correct character decoding
             return False, f"Dictionary not found: {self.dict_path}"

        try:
            from paddleocr import PaddleOCR
            # Initialize PaddleOCR with specific configurations for local ONNX execution
            self.ocr_engine = PaddleOCR(
                det_model_dir=self.det_model_dir,
                rec_model_dir=self.rec_model_dir,
                rec_char_dict_path=self.dict_path,
                use_angle_cls=False,  # Angle classification not needed for mostly upright receipts
                lang='en',
                use_onnx=True,        # Use ONNX Runtime for inference (often faster on CPU)
                device='cpu',
                enable_mkldnn=True    # Intel CPU optimization
            )
            self.is_loaded = True
            return True, "Model loaded successfully"
        except Exception as e:
            return False, str(e)

    def scan_image(self, image_path):
        """
        Scans a single image using the loaded OCR engine.
        
        Args:
            image_path (str): Full path to the image file.
            
        Returns:
            (dict, list): A tuple containing:
                - Structured data dictionary (Vendor, Total, etc.)
                - List of raw text lines found in the image.
        """
        if not self.ocr_engine:
            raise Exception("Model not loaded")

        # Run inference
        result = self.ocr_engine.ocr(image_path, cls=False)
        
        # --- Result Normalization ---
        # Different versions of PaddleOCR return results differently (list of lists vs list of objects).
        # This logic standardizes the output to a simple list of lines.
        
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            # Case 1: Result is a list of objects/dicts (newer PaddleOCR/PaddleX)
            if hasattr(first_item, 'keys') or isinstance(first_item, dict):
                 keys = getattr(first_item, 'keys', lambda: first_item.keys())()
                 if 'dt_polys' in keys and 'rec_texts' in keys and 'rec_scores' in keys:
                        boxes = first_item['dt_polys']
                        texts = first_item['rec_texts']
                        scores = first_item['rec_scores']
                        lines = []
                        for box, text, score in zip(boxes, texts, scores):
                            lines.append([box, (text, score)])
                        result = [lines]
            # Case 2: Result is a flat list of coordinates (older versions edge case)
            elif isinstance(first_item, list) and len(first_item) > 0:
                 try:
                    if isinstance(first_item[0][0], (int, float)):
                         result = [result]
                 except:
                    pass

        # Extract just the text content from the normalized result
        extracted_lines = []
        if result and result[0]:
            for line in result[0]:
                text_content = line[1][0] # line[1] is (text, confidence)
                extracted_lines.append(text_content)
        
        # Use the excel_exporter heuristics to extract structured info from the raw lines
        data = excel_exporter.extract_info(extracted_lines, os.path.basename(image_path))
        return data, extracted_lines

    def save_results(self, all_data, output_excel_path):
        """
        Saves a list of extracted data dictionaries to an Excel file.
        Delegates to the excel_exporter module.
        """
        excel_exporter.save_all_to_excel(all_data, output_excel_path)
