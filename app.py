import functools
import sqlite3
import subprocess
import threading
import logging
from flask import Flask, render_template, request, redirect, url_for, g, flash, session
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DATABASE = 'instance/bcpea.db'

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

COURT_CHOICES = [
    (0, 'All Courts'), (1, 'Благоевград'), (2, 'Бургас'), (3, 'Варна'), (4, 'Велико Търново'),
    (5, 'Видин'), (6, 'Враца'), (7, 'Габрово'), (8, 'Добрич'), (9, 'Кърджали'),
    (10, 'Кюстендил'), (11, 'Ловеч'), (12, 'Монтана'), (13, 'Пазарджик'),
    (14, 'Перник'), (15, 'Плевен'), (16, 'Пловдив'), (17, 'Разград'),
    (18, 'Русе'), (19, 'Силистра'), (20, 'Сливен'), (21, 'Смолян'),
    (22, 'София град'), (23, 'София окръг'), (24, 'Стара Загора'),
    (25, 'Търговище'), (26, 'Хасково'), (27, 'Шумен'), (28, 'Ямбол')
]

FILTER_TYPES = [
    ('property', 'Properties'),
    ('vehicle', 'Vehicles')
]

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Create auth_user table with status column
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auth_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create default admin user
        cursor.execute('''
            INSERT OR IGNORE INTO auth_user (name, email, password, status)
            VALUES ('Admin', 'admin@example.com', ?, 'approved')
        ''', (generate_password_hash('admin123'),))
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS filter_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'property',
                court INTEGER NOT NULL,
                settlements TEXT,
                excluded_property_types TEXT,
                blacklist TEXT,
                required_title_words TEXT,
                required_description_words TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_filters (
                user_id INTEGER,
                filter_group_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES auth_user(id) ON DELETE CASCADE,
                FOREIGN KEY(filter_group_id) REFERENCES filter_groups(id) ON DELETE CASCADE,
                PRIMARY KEY(user_id, filter_group_id)
            )
        ''')
        
        db.commit()

init_db()

# ================== AUTHENTICATION ROUTES ==================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('❌ Passwords do not match', 'error')
            return render_template('register.html')
            
        db = get_db()
        try:
            hashed_pw = generate_password_hash(password)
            db.execute('''
                INSERT INTO auth_user (name, email, password)
                VALUES (?, ?, ?)
            ''', (name, email, hashed_pw))
            db.commit()
            
            # Automatically log in the user after registration
            user = db.execute('SELECT * FROM auth_user WHERE email = ?', (email,)).fetchone()
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_status'] = user['status']
            
            flash('✅ Registration successful! Please wait for admin approval', 'success')
            return redirect(url_for('pending'))
        except sqlite3.IntegrityError:
            flash('❌ Email already registered', 'error')
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'error')
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        db = get_db()
        user = db.execute('SELECT * FROM auth_user WHERE email = ?', (email,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_status'] = user['status']
            
            if user['status'] == 'approved':
                flash('✅ Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                return redirect(url_for('pending'))
        else:
            flash('❌ Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('👋 You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/pending')
def pending():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if session.get('user_status') == 'approved':
        return redirect(url_for('index'))
    
    return render_template('pending.html')

# ================== ADMIN ROUTES ==================
@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session.get('user_email') != 'admin@example.com':
        flash('🔒 Admin access required', 'error')
        return redirect(url_for('login'))
    
    db = get_db()
    users = db.execute('SELECT * FROM auth_user ORDER BY created_at DESC').fetchall()
    return render_template('admin_users.html', users=users)

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
def admin_approve(user_id):
    if 'user_id' not in session or session.get('user_email') != 'admin@example.com':
        flash('🔒 Admin access required', 'error')
        return redirect(url_for('login'))
    
    db = get_db()
    try:
        db.execute('UPDATE auth_user SET status = "approved" WHERE id = ?', (user_id,))
        db.commit()
        flash('✅ User approved successfully', 'success')
    except Exception as e:
        flash(f'❌ Error approving user: {str(e)}', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/reject/<int:user_id>', methods=['POST'])
def admin_reject(user_id):
    if 'user_id' not in session or session.get('user_email') != 'admin@example.com':
        flash('🔒 Admin access required', 'error')
        return redirect(url_for('login'))
    
    db = get_db()
    try:
        db.execute('DELETE FROM auth_user WHERE id = ?', (user_id,))
        db.commit()
        flash('✅ User rejected successfully', 'success')
    except Exception as e:
        flash(f'❌ Error rejecting user: {str(e)}', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/trigger_scraper', methods=['POST'])
def admin_trigger_scraper():
    if 'user_id' not in session or session.get('user_email') != 'admin@example.com':
        flash('🔒 Admin access required', 'error')
        return redirect(url_for('login'))
    
    def run_scraper():
        try:
            result = subprocess.run(
                ['/app/venv/bin/python', 'scraper.py'],
                capture_output=True,
                text=True,
                timeout=1200  # 20 minutes timeout
            )
            app.logger.info(f"Scraper output: {result.stdout}")
            if result.stderr:
                app.logger.error(f"Scraper errors: {result.stderr}")
        except Exception as e:
            app.logger.error(f"Error running scraper: {str(e)}")
    
    # Run in a separate thread to avoid blocking
    thread = threading.Thread(target=run_scraper)
    thread.start()
    
    flash('✅ Scraper triggered successfully. Check logs for details.', 'success')
    return redirect(url_for('admin_users'))

# ================== AUTHENTICATION MIDDLEWARE ==================
def login_required(f):
    @functools.wraps(f)  # Preserve the original function's name
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('🔒 Please login to access this page', 'error')
            return redirect(url_for('login'))
        if session.get('user_status') != 'approved':
            return redirect(url_for('pending'))
        return f(*args, **kwargs)
    return decorated_function

# ================== PROTECTED ROUTES ==================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        email = request.form['email']
        db = get_db()
        try:
            db.execute('INSERT INTO auth_user (name, email, password) VALUES (?, ?, ?)', 
                      ('New User', email, generate_password_hash('temp_password')))
            db.commit()
            flash('✅ User added successfully', 'success')
        except sqlite3.IntegrityError:
            flash('❌ User already exists', 'error')
        return redirect(url_for('users'))
    return render_template('add_user.html')

@app.route('/users')
@login_required
def users():
    db = get_db()
    users = db.execute('SELECT * FROM auth_user ORDER BY created_at DESC').fetchall()
    return render_template('users.html', users=users)

@app.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    db = get_db()
    try:
        db.execute('DELETE FROM auth_user WHERE id = ?', (user_id,))
        db.commit()
        flash('✅ User deleted successfully', 'success')
    except Exception as e:
        flash(f'❌ Error deleting user: {str(e)}', 'error')
    return redirect(url_for('users'))

@app.route('/add_filter', methods=['GET', 'POST'])
@login_required
def add_filter():
    db = get_db()
    if request.method == 'POST':
        try:
            # Validate court selection
            court = request.form['court']
            if not court.isdigit() or int(court) not in [c[0] for c in COURT_CHOICES]:
                flash('❌ Invalid court selection', 'error')
                return redirect(url_for('add_filter'))

            # Process other form data
            filter_type = request.form['type']
            settlements = [s.strip() for s in request.form.getlist('settlements[]') if s.strip()]
            excluded = [e.strip() for e in request.form.getlist('excluded[]') if e.strip()]
            blacklist = [b.strip() for b in request.form.getlist('blacklist[]') if b.strip()]
            req_title = [t.strip() for t in request.form.getlist('required_title[]') if t.strip()]
            req_desc = [d.strip() for d in request.form.getlist('required_description[]') if d.strip()]
            user_emails = request.form.getlist('user_emails')

            # Insert into database
            cursor = db.cursor()
            cursor.execute('''
                INSERT INTO filter_groups (
                    type, court, settlements, excluded_property_types,
                    blacklist, required_title_words, required_description_words
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                filter_type,
                court,
                ','.join(settlements) if settlements else None,
                ','.join(excluded) if excluded else None,
                ','.join(blacklist) if blacklist else None,
                ','.join(req_title) if req_title else None,
                ','.join(req_desc) if req_desc else None
            ))
            
            # Handle user associations
            fg_id = cursor.lastrowid
            for email in user_emails:
                user = db.execute('SELECT id FROM auth_user WHERE email = ?', (email,)).fetchone()
                if user:
                    db.execute('INSERT INTO user_filters VALUES (?, ?)', (user['id'], fg_id))
            
            db.commit()
            flash('✅ Filter group created successfully', 'success')
            return redirect(url_for('filters'))
        
        except Exception as e:
            db.rollback()
            flash(f'❌ Error creating filter: {str(e)}', 'error')
            return redirect(url_for('add_filter'))
    
    # GET request handling
    users = db.execute('SELECT * FROM auth_user ORDER BY email').fetchall()
    return render_template('add_filter.html', 
                         court_choices=COURT_CHOICES, 
                         filter_types=FILTER_TYPES, 
                         users=users)

@app.route('/edit_filter/<int:filter_id>', methods=['GET', 'POST'])
@login_required
def edit_filter(filter_id):
    db = get_db()
    filter_group = db.execute('SELECT * FROM filter_groups WHERE id = ?', (filter_id,)).fetchone()
    
    if request.method == 'POST':
        try:
            # Validate court selection
            court = request.form['court']
            if not court.isdigit() or int(court) not in [c[0] for c in COURT_CHOICES]:
                flash('❌ Invalid court selection', 'error')
                return redirect(url_for('edit_filter', filter_id=filter_id))

            # Process form data
            filter_type = request.form['type']
            settlements = [s.strip() for s in request.form.getlist('settlements[]') if s.strip()]
            excluded = [e.strip() for e in request.form.getlist('excluded[]') if e.strip()]
            blacklist = [b.strip() for b in request.form.getlist('blacklist[]') if b.strip()]
            req_title = [t.strip() for t in request.form.getlist('required_title[]') if t.strip()]
            req_desc = [d.strip() for d in request.form.getlist('required_description[]') if d.strip()]
            user_emails = request.form.getlist('user_emails')

            # Update database
            db.execute('''
                UPDATE filter_groups 
                SET type = ?,
                    court = ?,
                    settlements = ?,
                    excluded_property_types = ?,
                    blacklist = ?,
                    required_title_words = ?,
                    required_description_words = ?
                WHERE id = ?
            ''', (
                filter_type,
                court,
                ','.join(settlements) if settlements else None,
                ','.join(excluded) if excluded else None,
                ','.join(blacklist) if blacklist else None,
                ','.join(req_title) if req_title else None,
                ','.join(req_desc) if req_desc else None,
                filter_id
            ))

            # Update user associations
            db.execute('DELETE FROM user_filters WHERE filter_group_id = ?', (filter_id,))
            for email in user_emails:
                user = db.execute('SELECT id FROM auth_user WHERE email = ?', (email,)).fetchone()
                if user:
                    db.execute('INSERT INTO user_filters VALUES (?, ?)', (user['id'], filter_id))
            
            db.commit()
            flash('✅ Filter group updated successfully', 'success')
            return redirect(url_for('filters'))
        
        except Exception as e:
            db.rollback()
            flash(f'❌ Error updating filter: {str(e)}', 'error')
            return redirect(url_for('edit_filter', filter_id=filter_id))

    # GET request handling
    users = db.execute('''
        SELECT u.email 
        FROM auth_user u
        JOIN user_filters uf ON u.id = uf.user_id
        WHERE uf.filter_group_id = ?
    ''', (filter_id,)).fetchall()
    associated_emails = [u['email'] for u in users]

    all_users = db.execute('SELECT * FROM auth_user ORDER BY email').fetchall()
    
    return render_template('edit_filter.html',
                         filter=filter_group,
                         court_choices=COURT_CHOICES,
                         filter_types=FILTER_TYPES,
                         users=all_users,
                         associated_emails=associated_emails)

@app.route('/delete_filter/<int:filter_id>', methods=['POST'])
@login_required
def delete_filter(filter_id):
    db = get_db()
    try:
        db.execute('DELETE FROM filter_groups WHERE id = ?', (filter_id,))
        db.commit()
        flash('✅ Filter group deleted successfully', 'success')
    except Exception as e:
        flash(f'❌ Error deleting filter: {str(e)}', 'error')
    return redirect(url_for('filters'))

@app.route('/filters')
@login_required
def filters():
    db = get_db()
    filters = db.execute('''
        SELECT fg.*, group_concat(u.email, ', ') as users
        FROM filter_groups fg
        LEFT JOIN user_filters uf ON fg.id = uf.filter_group_id
        LEFT JOIN auth_user u ON uf.user_id = u.id
        GROUP BY fg.id
        ORDER BY fg.created_at DESC
    ''').fetchall()
    return render_template('filters.html', 
                         filters=filters,
                         court_choices=dict(COURT_CHOICES),
                         filter_types=dict(FILTER_TYPES))


if __name__ == '__main__':
    app.run(host= '0.0.0.0', debug=True)
