from flask import Flask
from flask_cors import CORS
from app.api import api
import os


def create_app():
    app = Flask(__name__)
    CORS(app)
   # Instantiate the appropriate configuration object
    # app.config.from_object(Config())

    # Register blueprints, routes, and other Flask app configurations
    app.register_blueprint(api)

    # Other Flask configurations
    # ...

    return app


if __name__ == '__main__':
    app = create_app()
    port = os.environ.get("PORT", 8080)
    app.run(host='0.0.0.0', port=port)
