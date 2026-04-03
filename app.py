"""
OptimumTravelMapping — Flask application entry point.
"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from api.routes import api_bp
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)

app = Flask(__name__)
app.config.from_object(Config)

# Allow GitHub Pages and local development origins
CORS(app, origins=Config.CORS_ORIGINS, supports_credentials=False)

app.register_blueprint(api_bp, url_prefix='/api')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
