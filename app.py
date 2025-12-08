import os
import threading
import time
from flask import Flask, render_template, request, jsonify, send_file
# Standard Flask imports for web server, template rendering, request handling, and file serving.
# threading is used to run the OCR scan in the background so the UI doesn't freeze.

print("PippoCoca") # Debug print to verify module loading
from ocr_service import ReceiptScanner
import io
print("inapura") # Debug print

# Initialize the Flask application
app = Flask(__name__)
# Initialize the OCR scanner service (defined in ocr_service.py)
scanner = ReceiptScanner()

# Global state dictionary to track the progress of the scanning operation.
# This allows the frontend to poll for status updates (percentage complete, current file, etc.).
scan_state = {
    'is_scanning': False, # Flag to check if a scan is currently running
    'total': 0,           # Total number of files to scan
    'current': 0,         # Current file index being processed
    'results': [],        # List to store the extracted data for the frontend table
    'error': None         # To store any error messages if the scan fails
}

# List to track filenames uploaded in the current active session.
uploaded_files = []

# Define the directory where uploaded images will be temporarily stored.
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images_to_read')
# Create the directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Define output filenames for the results
RESULTS_FILE = "receipts_data.xlsx"
RAW_LOG_FILE = "ocr_raw_data.txt"

@app.route('/')
def index():
    """
    Renders the main page of the application.
    """
    return render_template('index.html')

@app.route('/reset', methods=['POST'])
def reset_session():
    """
    Resets the session state.
    Clears the list of uploaded files and deletes the physical files from the upload directory.
    This ensures a clean slate for a new batch of receipts.
    """
    global uploaded_files
    uploaded_files = []
    
    # Clean the directory to ensure only current session files exist physically
    try:
        for f in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, f)
            if os.path.isfile(file_path):
                os.unlink(file_path) # Delete the file
    except Exception as e:
        print(f"Error cleaning upload folder: {e}")
        
    return jsonify({"status": "success", "message": "Session reset"})

@app.route('/load_model', methods=['POST'])
def load_model():
    """
    Endpoint to trigger the loading of the OCR machine learning models.
    This can take a few seconds, so it's separated from the app startup or scan start.
    """
    success, message = scanner.load_model()
    if success:
        return jsonify({"status": "success", "message": message})
    else:
        return jsonify({"status": "error", "message": message}), 500

@app.route('/upload', methods=['POST'])
def upload_files():
    """
    Handles file uploads.
    Accepts multiple files, saves them to the UPLOAD_FOLDER, and tracks them in the 'uploaded_files' list.
    """
    if 'files[]' not in request.files:
        return jsonify({"status": "error", "message": "No files part"}), 400
    
    files = request.files.getlist('files[]')
    saved_count = 0
    
    global uploaded_files
    
    for file in files:
        if file.filename == '':
            continue
        if file:
            filename = file.filename
            # Avoid path traversal vulnerabilities by using os.path.basename
            filename = os.path.basename(filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            
            if filename not in uploaded_files:
                uploaded_files.append(filename)
            
            saved_count += 1
            
    return jsonify({"status": "success", "count": saved_count})

def run_scan_thread():
    """
    The main logic for processing receipts, designed to run in a separate thread.
    It iterates through uploaded files, calls the OCR scanner, updates the global 'scan_state',
    and finally saves the results to Excel and a text log.
    """
    global scan_state
    global uploaded_files
    
    scan_state['is_scanning'] = True
    scan_state['error'] = None
    scan_state['results'] = []
    
    try:
        supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
        
        # Filter files to ensure we only process supported image formats
        files = [f for f in uploaded_files if f.lower().endswith(supported_extensions)]
        
        scan_state['total'] = len(files)
        scan_state['current'] = 0
        
        all_data = []
        raw_text_content = "=== OCR RAW DATA LOG ===\n"
        
        for i, filename in enumerate(files):
            scan_state['current'] = i + 1
            image_path = os.path.join(UPLOAD_FOLDER, filename)
            
            try:
                # Perform the OCR scan on the individual image
                data, extracted_lines = scanner.scan_image(image_path)
                all_data.append(data)
                
                # Append raw text to the log string for debugging/auditing
                raw_text_content += f"\n--- START {filename} ---\n"
                for line in extracted_lines:
                    raw_text_content += f"{line}\n"
                raw_text_content += f"--- END {filename} ---\n"
                
                # Update results for the frontend to fetch incrementally
                scan_state['results'].append(data)
                
            except Exception as e:
                print(f"Error scanning {filename}: {e}")
                # We catch exceptions per file to ensure one failure doesn't stop the whole batch
        
        # Save structured data to Excel
        scanner.save_results(all_data, RESULTS_FILE)
        
        # Save raw OCR text to a .txt file
        with open(RAW_LOG_FILE, "w", encoding="utf-8") as f:
            f.write(raw_text_content)
            
    except Exception as e:
        scan_state['error'] = str(e)
    finally:
        # Mark scanning as complete regardless of success or failure
        scan_state['is_scanning'] = False

@app.route('/scan', methods=['POST'])
def start_scan():
    """
    Endpoint to start the scanning process.
    Checks if a scan is already running or if the model isn't loaded.
    Starts the 'run_scan_thread' in the background.
    """
    if scan_state['is_scanning']:
        return jsonify({"status": "error", "message": "Scan already in progress"}), 400
    
    if not scanner.is_loaded:
        return jsonify({"status": "error", "message": "Model not loaded"}), 400

    # Start the scanning logic in a separate thread to prevent blocking the HTTP request
    thread = threading.Thread(target=run_scan_thread)
    thread.start()
    return jsonify({"status": "success", "message": "Scanning started"})

@app.route('/status', methods=['GET'])
def get_status():
    """
    Returns the current state of the scanning process (progress, current results).
    Used by the frontend to poll for updates.
    """
    return jsonify(scan_state)

@app.route('/download/excel')
def download_excel():
    """
    Allows the user to download the generated Excel report.
    """
    if os.path.exists(RESULTS_FILE):
        return send_file(RESULTS_FILE, as_attachment=True)
    return "File not found", 404

@app.route('/download/txt')
def download_txt():
    """
    Allows the user to download the raw text logs.
    """
    if os.path.exists(RAW_LOG_FILE):
        return send_file(RAW_LOG_FILE, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
