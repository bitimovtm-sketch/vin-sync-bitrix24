from flask import Flask
from vin_sync import vin_bp

app = Flask(__name__)
app.register_blueprint(vin_bp)

if __name__ == '__main__':
    app.run()
