import sys
import os
from pathlib import Path

# Ensure parent is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from backend.app import app
except ImportError as e:
    # If import fails, create a minimal error handler
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/submit-feedback', methods=['POST'])
    def error_handler():
        return jsonify(error=f'Import error: {str(e)}'), 500
