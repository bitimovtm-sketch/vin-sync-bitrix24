import logging
from flask import Flask
from vin_sync import vin_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

app = Flask(__name__)
app.register_blueprint(vin_bp)

if __name__ == '__main__':
    app.run()
