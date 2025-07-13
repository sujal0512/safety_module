from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import sqlite3, os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'your_secret_key'  # Needed for flash messages

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize DB
def init_db():
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trainings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    date TEXT,
                    file TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS gear_distribution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_name TEXT,
                    gear_item TEXT,
                    date TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    search = request.args.get('search', '')
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    if search:
        c.execute("SELECT * FROM trainings WHERE title LIKE ?", ('%' + search + '%',))
        trainings = c.fetchall()
        c.execute("SELECT * FROM gear_distribution WHERE employee_name LIKE ? OR gear_item LIKE ?", 
                  ('%' + search + '%', '%' + search + '%'))
        gear = c.fetchall()
    else:
        c.execute("SELECT * FROM trainings")
        trainings = c.fetchall()
        c.execute("SELECT * FROM gear_distribution")
        gear = c.fetchall()
    conn.close()
    return render_template("dashboard.html", trainings=trainings, gear=gear, search=search)

@app.route('/add_training', methods=['GET', 'POST'])
def add_training():
    if request.method == 'GET':
        return render_template('add_training.html')
    if request.method == 'POST':
        title = request.form['title']
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            conn = sqlite3.connect('safety.db')
            c = conn.cursor()
            c.execute("INSERT INTO trainings (title, date, file) VALUES (?, ?, ?)",
                      (title, datetime.now().strftime("%Y-%m-%d"), filename))
            conn.commit()
            conn.close()
            flash('Training added successfully!', 'success')
            return redirect(url_for('dashboard'))  
        else:
            flash('Invalid file type', 'danger')
            return render_template('add_training.html')
    return render_template('add_training.html')

@app.route('/edit_training/<int:id>', methods=['GET', 'POST'])
def edit_training(id):
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # Remove old file
            c.execute("SELECT file FROM trainings WHERE id = ?", (id,))
            old_file = c.fetchone()
            if old_file and old_file[0]:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_file[0])
                if os.path.exists(old_path):
                    os.remove(old_path)
            c.execute("UPDATE trainings SET title=?, file=? WHERE id=?", (title, filename, id))
        else:
            c.execute("UPDATE trainings SET title=? WHERE id=?", (title, id))
        conn.commit()
        conn.close()
        flash('Training updated!', 'success')
        return redirect(url_for('dashboard'))
    else:
        c.execute("SELECT * FROM trainings WHERE id=?", (id,))
        training = c.fetchone()
        conn.close()
        return render_template('edit_training.html', training=training)

@app.route('/add_gear', methods=['POST'])
def add_gear():
    employee = request.form['employee']
    gear = request.form['gear']
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute("INSERT INTO gear_distribution (employee_name, gear_item, date) VALUES (?, ?, ?)",
              (employee, gear, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()
    flash('Gear distribution added!', 'success')
    return redirect(url_for('dashboard'))  

@app.route('/edit_gear/<int:id>', methods=['GET', 'POST'])
def edit_gear(id):
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    if request.method == 'POST':
        employee = request.form['employee']
        gear = request.form['gear']
        c.execute("UPDATE gear_distribution SET employee_name=?, gear_item=? WHERE id=?", (employee, gear, id))
        conn.commit()
        conn.close()
        flash('Gear distribution updated!', 'success')
        return redirect(url_for('dashboard'))
    else:
        c.execute("SELECT * FROM gear_distribution WHERE id=?", (id,))
        gear_item = c.fetchone()
        conn.close()
        return render_template('edit_gear.html', gear_item=gear_item)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete_training/<int:id>', methods=['POST'])
def delete_training(id):
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute("SELECT file FROM trainings WHERE id = ?", (id,))
    row = c.fetchone()
    if row and row[0]:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], row[0])
        if os.path.exists(file_path):
            os.remove(file_path)
    c.execute("DELETE FROM trainings WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Training deleted!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_gear/<int:id>', methods=['POST'])
def delete_gear(id):
    conn = sqlite3.connect('safety.db')
    c = conn.cursor()
    c.execute("DELETE FROM gear_distribution WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Gear distribution deleted!', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
