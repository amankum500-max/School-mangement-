# app/__init__.py
from flask import Flask
from config import Config
from extensions import socketio

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    socketio.init_app(app)

    # Blueprints Import
    from app.auth.routes import auth_bp
    from app.students.routes import students_bp
    from app.fees.routes import fees_bp  # <--- NAYA IMPORT
    
    # Blueprints Register
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(fees_bp)      # <--- NAYA REGISTER
    
    return app
