from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, g
import sqlite3, os, logging
from datetime import datetime
from werkzeug.utils import secure_filename

# Configuration
DATABASE = os.path.join(os.path.dirname(__file__), 'safety.db')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
SECRET_KEY = 'your_secret_key'
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Logging setup
logging.basicConfig(level=logging.INFO)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

@app.teardown_appcontext
def close_db(_):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS trainings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        date TEXT NOT NULL,
                        file TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS gear_distribution (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_name TEXT NOT NULL,
                        gear_item TEXT NOT NULL,
                        date TEXT NOT NULL
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS incidents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        description TEXT NOT NULL,
                        reported_by TEXT NOT NULL,
                        date TEXT NOT NULL
                    )''')
        conn.commit()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    search = request.args.get('search', '').strip()
    db = get_db()
    c = db.cursor()
    if search:
        c.execute("SELECT * FROM trainings WHERE title LIKE ?", ('%' + search + '%',))
        trainings = c.fetchall()
        c.execute("SELECT * FROM gear_distribution WHERE employee_name LIKE ? OR gear_item LIKE ?", 
                  ('%' + search + '%', '%' + search + '%'))
        gear = c.fetchall()
        c.execute("SELECT * FROM incidents WHERE description LIKE ? OR reported_by LIKE ?", 
                  ('%' + search + '%', '%' + search + '%'))
        incidents = c.fetchall()
    else:
        c.execute("SELECT * FROM trainings")
        trainings = c.fetchall()
        c.execute("SELECT * FROM gear_distribution")
        gear = c.fetchall()
        c.execute("SELECT * FROM incidents ORDER BY date DESC")
        incidents = c.fetchall()
    return render_template("dashboard.html", trainings=trainings, gear=gear, incidents=incidents, search=search)

@app.route('/add_training', methods=['GET', 'POST'])
def add_training():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        file = request.files.get('file')
        if not title:
            flash('Title is required.', 'danger')
            return render_template('add_training.html')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            db = get_db()
            c = db.cursor()
            c.execute("INSERT INTO trainings (title, date, file) VALUES (?, ?, ?)",
                      (title, datetime.now().strftime("%Y-%m-%d"), filename))
            db.commit()
            logging.info(f"Training '{title}' added with file '{filename}'.")
            flash('Training added successfully!', 'success')
            return redirect(url_for('dashboard'))  
        else:
            flash('Invalid file type or missing file.', 'danger')
    return render_template('add_training.html')

@app.route('/edit_training/<int:id>', methods=['GET', 'POST'])
def edit_training(id):
    db = get_db()
    c = db.cursor()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        file = request.files.get('file')
        if not title:
            flash('Title is required.', 'danger')
            return redirect(url_for('edit_training', id=id))
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            c.execute("SELECT file FROM trainings WHERE id = ?", (id,))
            old_file = c.fetchone()
            if old_file and old_file[0]:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_file[0])
                if os.path.exists(old_path):
                    os.remove(old_path)
            c.execute("UPDATE trainings SET title=?, file=? WHERE id=?", (title, filename, id))
        else:
            c.execute("UPDATE trainings SET title=? WHERE id=?", (title, id))
        db.commit()
        logging.info(f"Training '{title}' updated (ID: {id}).")
        flash('Training updated!', 'success')
        return redirect(url_for('dashboard'))
    else:
        c.execute("SELECT * FROM trainings WHERE id=?", (id,))
        training = c.fetchone()
        return render_template('edit_training.html', training=training)

@app.route('/add_gear', methods=['POST'])
def add_gear():
    employee = request.form.get('employee', '').strip()
    gear = request.form.get('gear', '').strip()
    if not employee or not gear:
        flash('Employee and gear item are required.', 'danger')
        return redirect(url_for('dashboard'))
    db = get_db()
    c = db.cursor()
    c.execute("INSERT INTO gear_distribution (employee_name, gear_item, date) VALUES (?, ?, ?)",
              (employee, gear, datetime.now().strftime("%Y-%m-%d")))
    db.commit()
    logging.info(f"Gear '{gear}' distributed to '{employee}'.")
    flash('Gear distribution added!', 'success')
    return redirect(url_for('dashboard'))  

@app.route('/edit_gear/<int:id>', methods=['GET', 'POST'])
def edit_gear(id):
    db = get_db()
    c = db.cursor()
    if request.method == 'POST':
        employee = request.form.get('employee', '').strip()
        gear = request.form.get('gear', '').strip()
        if not employee or not gear:
            flash('Employee and gear item are required.', 'danger')
            return redirect(url_for('edit_gear', id=id))
        c.execute("UPDATE gear_distribution SET employee_name=?, gear_item=? WHERE id=?", (employee, gear, id))
        db.commit()
        logging.info(f"Gear distribution updated (ID: {id}).")
        flash('Gear distribution updated!', 'success')
        return redirect(url_for('dashboard'))
    else:
        c.execute("SELECT * FROM gear_distribution WHERE id=?", (id,))
        gear_item = c.fetchone()
        return render_template('edit_gear.html', gear_item=gear_item)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete_training/<int:id>', methods=['POST'])
def delete_training(id):
    db = get_db()
    c = db.cursor()
    c.execute("SELECT file FROM trainings WHERE id = ?", (id,))
    row = c.fetchone()
    if row and row[0]:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], row[0])
        if os.path.exists(file_path):
            os.remove(file_path)
    c.execute("DELETE FROM trainings WHERE id = ?", (id,))
    db.commit()
    logging.info(f"Training deleted (ID: {id}).")
    flash('Training deleted!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_gear/<int:id>', methods=['POST'])
def delete_gear(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM gear_distribution WHERE id = ?", (id,))
    db.commit()
    logging.info(f"Gear distribution deleted (ID: {id}).")
    flash('Gear distribution deleted!', 'success')
    return redirect(url_for('dashboard'))

# Incident Reporting routes (moved outside __main__)
@app.route('/incidents', methods=['GET', 'POST'])
def incidents():
    db = get_db()
    c = db.cursor()
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        reported_by = request.form.get('reported_by', '').strip()
        if not description or not reported_by:
            flash('Description and reporter name are required.', 'danger')
        else:
            c.execute("INSERT INTO incidents (description, reported_by, date) VALUES (?, ?, ?)",
                      (description, reported_by, datetime.now().strftime("%Y-%m-%d")))
            db.commit()
            logging.info(f"Incident reported by '{reported_by}'.")
            flash('Incident reported!', 'success')
            return redirect(url_for('incidents'))
    c.execute("SELECT * FROM incidents ORDER BY date DESC")
    incidents = c.fetchall()
    return render_template('incidents.html', incidents=incidents)

@app.route('/delete_incident/<int:id>', methods=['POST'])
def delete_incident(id):
    db = get_db()
    c = db.cursor()
    c.execute("DELETE FROM incidents WHERE id = ?", (id,))
    db.commit()
    logging.info(f"Incident deleted (ID: {id}).")
    flash('Incident deleted!', 'success')
    return redirect(url_for('incidents'))

if __name__ == '__main__':
    app.run(debug=True)
