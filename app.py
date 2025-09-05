from flask import Flask
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
import os
from dotenv import load_dotenv
from database import db

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Ensure instance directory exists
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

# Use absolute path for database
db_path = os.path.join(instance_path, 'footmob.db')
print(f"Database path: {db_path}")
# Don't use DATABASE_URL from .env, use the calculated absolute path
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = ''

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

from routes.auth import auth_bp
from routes.groups import groups_bp
from routes.games import games_bp
from routes.invites import invites_bp
from routes.notifications import notifications_bp

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(groups_bp, url_prefix='/groups')
app.register_blueprint(games_bp, url_prefix='/games')
app.register_blueprint(invites_bp, url_prefix='/invites')
app.register_blueprint(notifications_bp, url_prefix='/api/notifications')

from routes.main import main_bp
app.register_blueprint(main_bp)

# Initialize database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)