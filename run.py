import eventlet
eventlet.monkey_patch()

from app import create_app
from extensions import socketio
from database import init_db

app = create_app()

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, port=5000)
