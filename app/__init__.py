from flask import Flask
from config import Config
from extensions import socketio

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    socketio.init_app(app)

    # Blueprints Import & Register (Modules)
    from app.auth.routes import auth_bp
    from app.students.routes import students_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    
    return app
