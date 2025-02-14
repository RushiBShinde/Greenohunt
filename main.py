from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Replace with a secure key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///treasurehunt.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# ---------------------------
# Models
# ---------------------------
class Team(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    current_step = db.Column(db.Integer, default=0)  # Tracks the progress (0 means no clue solved yet)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class TeamPath(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))
    sequence_number = db.Column(db.Integer)  # The order of the clue in the path
    location_code = db.Column(db.String(50))   # The value encoded in the QR code
    riddle = db.Column(db.Text)                # The riddle or clue text

# ---------------------------
# User Loader
# ---------------------------
@login_manager.user_loader
def load_user(user_id):
    return Team.query.get(int(user_id))

# ---------------------------
# Create DB tables (if not present)
# ---------------------------
def create_tables():
    db.create_all()

# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def index():
    return redirect(url_for('login'))

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        team_name = request.form.get('team_name')
        password = request.form.get('password')
        if Team.query.filter_by(team_name=team_name).first():
            flash('Team name already exists. Please choose a different name.')
            return redirect(url_for('register'))
        new_team = Team(team_name=team_name)
        new_team.set_password(password)
        db.session.add(new_team)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        team_name = request.form.get('team_name')
        password = request.form.get('password')
        team = Team.query.filter_by(team_name=team_name).first()
        if team and team.check_password(password):
            login_user(team)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid team name or password.')
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

# Dashboard – shows current progress and next riddle
@app.route('/dashboard')
@login_required
def dashboard():
    current_step = current_user.current_step
    # Get the next clue (sequence_number starts at 1)
    next_path = TeamPath.query.filter_by(team_id=current_user.id, sequence_number=current_step+1).first()
    return render_template('dashboard.html', current_step=current_step, next_path=next_path)

# Scan endpoint – validate QR code submission
@app.route('/scan', methods=['POST'])
@login_required
def scan():
    scanned_code = request.form.get('qr_code')
    current_step = current_user.current_step
    expected_path = TeamPath.query.filter_by(team_id=current_user.id, sequence_number=current_step+1).first()
    if expected_path and expected_path.location_code == scanned_code:
        current_user.current_step += 1
        db.session.commit()
        flash('Correct scan! Here is your next clue.')
    else:
        flash('Incorrect QR code scanned. Please try again.')
    return redirect(url_for('dashboard'))

# Admin route to load CSV data into TeamPath table.
# CSV file format: team_name,sequence_number,location_code,riddle
@app.route('/admin/load_csv')
def load_csv():
    csv_file = 'team_paths.csv'
    if not os.path.exists(csv_file):
        return "CSV file not found.", 404
    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            # Find the team by team_name (teams must register using the same team_name)
            team = Team.query.filter_by(team_name=row['team_name']).first()
            if team:
                # Avoid duplicate entries by checking if this sequence already exists
                existing = TeamPath.query.filter_by(team_id=team.id, sequence_number=int(row['sequence_number'])).first()
                if not existing:
                    new_path = TeamPath(
                        team_id=team.id,
                        sequence_number=int(row['sequence_number']),
                        location_code=row['location_code'],
                        riddle=row['riddle']
                    )
                    db.session.add(new_path)
                    count += 1
        db.session.commit()
    return f"Loaded {count} entries from CSV.", 200

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True, host='0.0.0.0')
