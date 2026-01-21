from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
from datetime import datetime
from functools import wraps
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key_here_change_in_production'

ITEMS_PER_PAGE = 10

def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create tables
conn = get_db_connection()
conn.execute("""
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    address TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Add default admin if doesn't exist
conn.execute("INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)", 
             ('admin', 'admin123'))
conn.commit()
conn.close()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please login first!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    if not phone:
        return True
    return len(phone) >= 10 and phone.isdigit()

def get_statistics():
    conn = get_db_connection()
    total = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
    active = conn.execute("SELECT COUNT(*) as count FROM users WHERE status='active'").fetchone()['count']
    inactive = conn.execute("SELECT COUNT(*) as count FROM users WHERE status='inactive'").fetchone()['count']
    conn.close()
    return {'total': total, 'active': active, 'inactive': inactive}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", 
                            (username, password)).fetchone()
        conn.close()
        
        if admin:
            session['admin_id'] = admin['id']
            session['username'] = admin['username']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out!', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    stats = get_statistics()
    return render_template('dashboard.html', stats=stats, username=session.get('username'))

@app.route('/')
@login_required
def index():
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'id')
        status_filter = request.args.get('status', 'all')
        
        conn = get_db_connection()
        
        # Build query
        query = "SELECT * FROM users WHERE 1=1"
        params = []
        
        if search:
            query += " AND (name LIKE ? OR email LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term])
        
        if status_filter != 'all':
            query += " AND status = ?"
            params.append(status_filter)
        
        # Sorting
        valid_sorts = ['id', 'name', 'email', 'phone', 'created_at']
        if sort_by not in valid_sorts:
            sort_by = 'id'
        query += f" ORDER BY {sort_by}"
        
        # Get total count
        count_query = "SELECT COUNT(*) as count FROM users WHERE 1=1"
        if search:
            count_query += " AND (name LIKE ? OR email LIKE ?)"
        if status_filter != 'all':
            count_query += " AND status = ?"
        
        total = conn.execute(count_query, params).fetchone()['count']
        total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        # Pagination
        offset = (page - 1) * ITEMS_PER_PAGE
        query += f" LIMIT {ITEMS_PER_PAGE} OFFSET {offset}"
        
        users = conn.execute(query, params).fetchall()
        conn.close()
        
        return render_template('index.html', 
                             users=users, 
                             page=page,
                             total_pages=total_pages,
                             search=search,
                             sort_by=sort_by,
                             status_filter=status_filter,
                             username=session.get('username'))
    except Exception as e:
        flash(f"Error: {e}", 'danger')
        return redirect(url_for('dashboard'))

@app.route('/add', methods=['POST'])
@login_required
def add_user():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    
    # Validation
    if not name or len(name) < 2:
        flash('Name must be at least 2 characters!', 'danger')
        return redirect(url_for('index'))
    
    if not validate_email(email):
        flash('Invalid email format!', 'danger')
        return redirect(url_for('index'))
    
    if phone and not validate_phone(phone):
        flash('Phone must be at least 10 digits!', 'danger')
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO users (name, email, phone, address) VALUES (?, ?, ?, ?)", 
                    (name, email, phone, address))
        conn.commit()
        conn.close()
        flash('User added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Email already exists!', 'danger')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_user(id):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM users WHERE id=?", (id,))
        conn.commit()
        conn.close()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update_user(id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (id,)).fetchone()
    
    if not user:
        flash('User not found!', 'danger')
        conn.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        status = request.form.get('status', 'active')
        
        # Validation
        if not name or len(name) < 2:
            flash('Name must be at least 2 characters!', 'danger')
            conn.close()
            return redirect(url_for('update_user', id=id))
        
        if not validate_email(email):
            flash('Invalid email format!', 'danger')
            conn.close()
            return redirect(url_for('update_user', id=id))
        
        if phone and not validate_phone(phone):
            flash('Phone must be at least 10 digits!', 'danger')
            conn.close()
            return redirect(url_for('update_user', id=id))
        
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                "UPDATE users SET name=?, email=?, phone=?, address=?, status=?, updated_at=? WHERE id=?",
                (name, email, phone, address, status, now, id)
            )
            conn.commit()
            conn.close()
            flash('User updated successfully!', 'success')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('Email already exists!', 'danger')
        except Exception as e:
            flash(f'Error: {e}', 'danger')
    
    conn.close()
    return render_template('update.html', user=user, username=session.get('username'))

@app.errorhandler(404)
def not_found(error):
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
