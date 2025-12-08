# ReceiptReader

This project is a neural OCR (Optical Character Recognition) system designed to scan receipts and invoices. It utilizes **PaddleOCR** with local **ONNX** models to extract key information (Date, Vendor, Total, Currency, Location) and export it to Excel.

The software offers two modes of operation:
1. **Web Interface (Flask):** A modern "Neon/Glass" UI for drag & drop uploading and real-time verification.
2. **CLI (Command Line):** A script for batch processing entire folders of images.

---

## 📋 Prerequisites & Folder Structure

The code is configured to look for resources in specific relative paths. It is crucial to maintain this structure or modify the paths in `main.py` and `ocr_service.py` accordingly.

### 1. Required Structure
The project expects to be located next to a `PaddleOCR_FineTune` folder containing the official PaddleOCR repository (needed for the character dictionary `en_dict.txt`).

```text
/Your_Workspace/
├── ReceiptReader/          <-- (This project folder)
│   ├── app.py
│   ├── main.py
│   ├── model_local_onnx/       <-- Recognition Model (ONNX)
│   ├── det_model_onnx/         <-- Detection Model (ONNX)
│   ├── images_to_read/         <-- (This is the folder for images to be processed)
│   └── ...
│
└── PaddleOCR_FineTune/         <-- (Sibling folder)
    └── PaddleOCR/              <-- Cloned repository
        └── ppocr/
            └── utils/
                └── en_dict.txt
```

### 2. Dependencies & Critical Versions

To avoid known conflicts (especially with Paddle and Numpy 2.0+), please install the specific versions listed below.

**Recommended Python Version:** 3.10

Create a `requirements.txt` file with the following content:

```text
Flask==3.0.0
pandas==2.2.0
openpyxl==3.1.2
paddleocr>=2.7.0
paddlepaddle==2.6.1         # Or 3.x beta if required by hardware, but 2.6.1 is stable for CPU
onnxruntime==1.17.1         # Essential for running the .onnx models
numpy==1.26.4               # CRITICAL: Must be < 2.0 for Paddle compatibility
opencv-python-headless
Shapely
```

---

## 🛠️ Installation

1. **Open your terminal** in the project folder:
   ```bash
   cd "/mnt/c/Users/Admin/Desktop/ReceiptReader"
   ```

2. **Create a Virtual Environment (Optional but recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *Note: If you haven't created the file yet, run:*
   ```bash
   pip install Flask pandas openpyxl paddleocr paddlepaddle onnxruntime "numpy<2.0" opencv-python-headless
   ```

4. **Verify Models and Dictionary:**
   Ensure that `.onnx` files are present in `det_model_onnx` and `model_local_onnx`, and that the dictionary exists in the relative path described above.

---

## 🚀 Usage: Web App (Recommended)

This mode provides a visual interface to upload files and view results.

1. **Start the server:**
   ```bash
   python app.py
   ```
2. **Open your browser:**
   Go to [http://localhost:5000](http://localhost:5000)
3. **Procedure:**
   - Click **"INITIALIZE SYSTEM"**. This loads the ONNX models into RAM (takes a few seconds).
   - Drag & drop receipt images into the upload area.
   - Click **"INITIATE SCAN"**.
   - Download the Excel report or TXT logs upon completion.

---

## 💻 Usage: CLI (Batch Mode)

Use this if you have a folder full of images and want to process them all at once without a GUI.

1. **Prepare images:**
   Put `.jpg`, `.png`, etc. files into the folder:
   `./images_to_read/`
   *(If the folder doesn't exist, the script will create it on the first run).*

2. **Run the script:**
   ```bash
   python main.py
   ```

3. **Results:**
   - Extracted data is saved to `receipts_data.xlsx`.
   - Raw OCR text is logged to `ocr_raw_data.txt`.

---

## ⚠️ Common Troubleshooting

**Error: `Dictionary not found`**
The code looks for the dictionary at `../PaddleOCR_FineTune/PaddleOCR/ppocr/utils/en_dict.txt`.
*Solution:* Clone PaddleOCR into the correct directory or modify `self.dict_path` in `ocr_service.py` and `DICT_PATH` in `main.py` to point to a local `en_dict.txt`.

**Error: `ImportError: numpy.core.multiarray failed to import`**
You have likely installed Numpy 2.0+.
*Solution:*
```bash
pip uninstall numpy
pip install "numpy<2.0"
```

**Error: `Model not loaded` in Web App**
You tried to scan without clicking "INITIALIZE SYSTEM" first. The model is loaded on-demand to save resources during startup.