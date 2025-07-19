from flask import (
    Flask, render_template, request, redirect, url_for, send_from_directory,
    flash, g, session, abort
)
import sqlite3, os, logging, uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from functools import wraps

# Config
DATABASE = os.path.join(os.path.dirname(__file__), 'safety.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
SECRET_KEY = 'your_secret_key'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logging.basicConfig(level=logging.INFO)

# ------------- UTILITY --------------

def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        return unique_filename
    return None

def get_db():
    if 'db' not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                file TEXT,
                downloads INTEGER DEFAULT 0
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS gear_distribution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name TEXT NOT NULL,
                gear_item TEXT NOT NULL,
                date TEXT NOT NULL
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                reported_by TEXT NOT NULL,
                date TEXT NOT NULL
            )''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )''')
        conn.commit()

        # Add default user
        c.execute("SELECT id FROM users WHERE username='admin'")
        if not c.fetchone():
            c.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ('admin', 'admin123')  # In real scenario, hash password!
            )
            conn.commit()
init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ------------- AUTH ROUTES --------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        if user:
            session['logged_in'] = True
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

# ------------- DASHBOARD --------------

@app.route('/', methods=['GET'])
@login_required
def dashboard():
    search = request.args.get('search', '').strip()
    db = get_db()

    if search:
        trainings = db.execute(
            "SELECT * FROM trainings WHERE title LIKE ? ORDER BY date DESC",
            ('%' + search + '%',)
        ).fetchall()
        gear = db.execute(
            "SELECT * FROM gear_distribution WHERE employee_name LIKE ? OR gear_item LIKE ? ORDER BY date DESC",
            ('%' + search + '%', '%' + search + '%')
        ).fetchall()
        incidents = db.execute(
            "SELECT * FROM incidents WHERE description LIKE ? OR reported_by LIKE ? ORDER BY date DESC",
            ('%' + search + '%', '%' + search + '%')
        ).fetchall()
    else:
        trainings = db.execute(
            "SELECT * FROM trainings ORDER BY date DESC"
        ).fetchall()
        gear = db.execute(
            "SELECT * FROM gear_distribution ORDER BY date DESC"
        ).fetchall()
        incidents = db.execute(
            "SELECT * FROM incidents ORDER BY date DESC"
        ).fetchall()

    stats = {
        'trainings': db.execute("SELECT COUNT(*) FROM trainings").fetchone()[0],
        'gear': db.execute("SELECT COUNT(*) FROM gear_distribution").fetchone()[0],
        'incidents': db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
    }
    return render_template('dashboard.html', trainings=trainings,
                           gear=gear, incidents=incidents, search=search, stats=stats)

# ------------- TRAINING CRUD -------------

@app.route('/add_training', methods=['GET', 'POST'])
@login_required
def add_training():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        file = request.files.get('file')
        if not title:
            flash('Title is required.', 'danger')
            return render_template('add_training.html')
        filename = save_uploaded_file(file)
        if not filename:
            flash('Invalid file type or missing file.', 'danger')
            return render_template('add_training.html')
        db = get_db()
        db.execute("INSERT INTO trainings (title, date, file) VALUES (?, ?, ?)",
                   (title, datetime.now().strftime("%Y-%m-%d"), filename))
        db.commit()
        flash('Training added successfully!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_training.html')

@app.route('/edit_training/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_training(id):
    db = get_db()
    training = db.execute("SELECT * FROM trainings WHERE id = ?", (id,)).fetchone()
    if not training:
        flash("Training not found.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        file = request.files.get('file')
        if not title:
            flash('Title is required.', 'danger')
            return render_template('edit_training.html', training=training)
        if file and allowed_file(file.filename):
            # Remove old file
            if training['file']:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], training['file'])
                if os.path.exists(old_path):
                    os.remove(old_path)
            filename = save_uploaded_file(file)
            db.execute("UPDATE trainings SET title=?, file=? WHERE id=?", (title, filename, id))
        else:
            db.execute("UPDATE trainings SET title=? WHERE id=?", (title, id))
        db.commit()
        flash('Training updated!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit_training.html', training=training)

@app.route('/delete_training/<int:id>', methods=['POST'])
@login_required
def delete_training(id):
    db = get_db()
    training = db.execute("SELECT * FROM trainings WHERE id = ?", (id,)).fetchone()
    if not training:
        abort(404)
    if training['file']:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], training['file'])
        if os.path.exists(file_path):
            os.remove(file_path)
    db.execute("DELETE FROM trainings WHERE id = ?", (id,))
    db.commit()
    flash('Training deleted!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    db = get_db()
    db.execute("UPDATE trainings SET downloads = downloads + 1 WHERE file = ?", (filename,))
    db.commit()
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------- GEAR CRUD -------------

@app.route('/add_gear', methods=['GET', 'POST'])
@login_required
def add_gear():
    if request.method == "POST":
        employee = request.form.get('employee', '').strip()
        gear = request.form.get('gear', '').strip()
        if not employee or not gear:
            flash('Employee name and gear item required.', 'danger')
            return render_template('add_gear.html')
        db = get_db()
        db.execute("INSERT INTO gear_distribution (employee_name, gear_item, date) VALUES (?, ?, ?)",
                   (employee, gear, datetime.now().strftime("%Y-%m-%d")))
        db.commit()
        flash('Gear distribution added!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('add_gear.html')

@app.route('/edit_gear/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_gear(id):
    db = get_db()
    gear_item = db.execute("SELECT * FROM gear_distribution WHERE id=?", (id,)).fetchone()
    if not gear_item:
        flash("Gear record not found.", "danger")
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        employee = request.form.get('employee', '').strip()
        gear = request.form.get('gear', '').strip()
        if not employee or not gear:
            flash('Employee and gear item are required.', 'danger')
            return render_template('edit_gear.html', gear_item=gear_item)
        db.execute("UPDATE gear_distribution SET employee_name=?, gear_item=? WHERE id=?", (employee, gear, id))
        db.commit()
        flash('Gear distribution updated!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit_gear.html', gear_item=gear_item)

@app.route('/delete_gear/<int:id>', methods=['POST'])
@login_required
def delete_gear(id):
    db = get_db()
    db.execute("DELETE FROM gear_distribution WHERE id=?", (id,))
    db.commit()
    flash('Gear distribution deleted!', 'success')
    return redirect(url_for('dashboard'))

# ------------- INCIDENTS --------------

@app.route('/incidents', methods=['GET', 'POST'])
@login_required
def incidents_view():
    db = get_db()
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        reported_by = request.form.get('reported_by', '').strip()
        if not description or not reported_by:
            flash('Description and reporter name are required.', 'danger')
        else:
            db.execute("INSERT INTO incidents (description, reported_by, date) VALUES (?, ?, ?)",
                       (description, reported_by, datetime.now().strftime("%Y-%m-%d")))
            db.commit()
            flash('Incident reported!', 'success')
            return redirect(url_for('incidents_view'))
    incidents = db.execute("SELECT * FROM incidents ORDER BY date DESC").fetchall()
    return render_template('incidents.html', incidents=incidents)

@app.route('/edit_incident/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_incident(id):
    db = get_db()
    incident = db.execute("SELECT * FROM incidents WHERE id=?", (id,)).fetchone()
    if not incident:
        flash("Incident not found.", "danger")
        return redirect(url_for('incidents_view'))
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        reported_by = request.form.get('reported_by', '').strip()
        if not description or not reported_by:
            flash('All fields required.', 'danger')
            return render_template('edit_incident.html', incident=incident)
        db.execute("UPDATE incidents SET description=?, reported_by=? WHERE id=?", (description, reported_by, id))
        db.commit()
        flash("Incident updated!", "success")
        return redirect(url_for('incidents_view'))
    return render_template('edit_incident.html', incident=incident)

@app.route('/delete_incident/<int:id>', methods=['POST'])
@login_required
def delete_incident(id):
    db = get_db()
    db.execute("DELETE FROM incidents WHERE id = ?", (id,))
    db.commit()
    flash('Incident deleted!', 'success')
    return redirect(url_for('incidents_view'))

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# ------------- MAIN --------------

if __name__ == '__main__':
    app.run(debug=True)
# This is the main entry point for the Flask application.
# It initializes the app and runs it in debug mode. 