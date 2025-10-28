from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, session
from datetime import datetime, timedelta
import os
import json
import csv
from io import StringIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import hashlib
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Email configuration - use environment variables
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_USE_TLS'] = True

# Simple file-based storage for persistence
DATA_FILE = 'data.json'
USERS_FILE = 'users.json'

def load_users():
    """Load users data from file"""
    try:
        if not os.path.exists(USERS_FILE):
            default_data = {'users': {}}
            with open(USERS_FILE, 'w') as f:
                json.dump(default_data, f, indent=2)
            return default_data
        
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading users: {e}")
        return {'users': {}}

def save_users(data):
    """Save users data to file"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving users: {e}")
        return False

def hash_password(password):
    """Hash password using SHA-256 with salt"""
    salt = secrets.token_hex(16)
    return hashlib.sha256((password + salt).encode()).hexdigest() + ':' + salt

def verify_password(stored_password, provided_password):
    """Verify password against stored hash"""
    try:
        hashed, salt = stored_password.split(':')
        return hashlib.sha256((provided_password + salt).encode()).hexdigest() == hashed
    except:
        return False

def send_verification_email(email, verification_token, username):
    """Send verification email to user"""
    try:
        # Check if email is configured
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            print("Email not configured - printing verification link to console")
            verification_link = f"{request.host_url}verify_email/{verification_token}"
            print(f"VERIFICATION LINK for {username} ({email}): {verification_link}")
            return True
            
        # For Render deployment, use the actual URL
        verification_link = f"{request.host_url}verify_email/{verification_token}"
        
        # Email content
        subject = "Verify Your Friendz Share Account"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                         color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                .button {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                         color: white; padding: 12px 30px; text-decoration: none; 
                         border-radius: 25px; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Friendz Share</h1>
                    <p>Share Expenses. Strengthen Friendships.</p>
                </div>
                <div class="content">
                    <h2>Welcome, {username}!</h2>
                    <p>Thank you for registering with Friendz Share. To start sharing expenses with your friends, please verify your email address by clicking the button below:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_link}" class="button">Verify Email Address</a>
                    </div>
                    
                    <p>If the button doesn't work, copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
                    
                    <p>This link will expire in 24 hours for security reasons.</p>
                    
                    <p>Happy sharing!<br>The Friendz Share Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = email
        msg['Subject'] = subject
        
        # Add HTML content
        msg.attach(MIMEText(html_content, 'html'))
        
        # Send email
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        
        print(f"Verification email sent to {email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        # Fallback: print verification link to console
        verification_link = f"{request.host_url}verify_email/{verification_token}"
        print(f"EMAIL FAILED - VERIFICATION LINK for {username} ({email}): {verification_link}")
        return False

def send_password_reset_email(email, reset_token, username):
    """Send password reset email to user"""
    try:
        # Check if email is configured
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            print("Email not configured - printing reset link to console")
            reset_link = f"{request.host_url}reset_password/{reset_token}"
            print(f"PASSWORD RESET LINK for {username} ({email}): {reset_link}")
            return True
            
        reset_link = f"{request.host_url}reset_password/{reset_token}"
        
        subject = "Reset Your Friendz Share Password"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); 
                         color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                .button {{ background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); 
                         color: white; padding: 12px 30px; text-decoration: none; 
                         border-radius: 25px; display: inline-block; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Friendz Share</h1>
                    <p>Password Reset Request</p>
                </div>
                <div class="content">
                    <h2>Hello, {username}!</h2>
                    <p>We received a request to reset your password. Click the button below to create a new password:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </div>
                    
                    <p>If the button doesn't work, copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; color: #ff6b6b;">{reset_link}</p>
                    
                    <p>This link will expire in 1 hour for security reasons.</p>
                    
                    <p>If you didn't request this reset, please ignore this email.</p>
                    
                    <p>Best regards,<br>The Friendz Share Team</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        
        print(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        print(f"Error sending reset email: {e}")
        # Fallback: print reset link to console
        reset_link = f"{request.host_url}reset_password/{reset_token}"
        print(f"EMAIL FAILED - PASSWORD RESET LINK for {username} ({email}): {reset_link}")
        return False

# ... (Keep all your existing data loading/saving functions)

def load_data():
    """Load data from file with proper error handling"""
    try:
        if not os.path.exists(DATA_FILE):
            default_data = {
                'groups': {},
                'expenses': {},
                'next_group_id': 1,
                'next_expense_id': 1,
                'recent_members': []
            }
            with open(DATA_FILE, 'w') as f:
                json.dump(default_data, f, indent=2)
            return default_data
        
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            
        required_keys = ['groups', 'expenses', 'next_group_id', 'next_expense_id', 'recent_members']
        for key in required_keys:
            if key not in data:
                if key == 'groups':
                    data[key] = {}
                elif key == 'expenses':
                    data[key] = {}
                elif key == 'recent_members':
                    data[key] = []
                else:
                    data[key] = 1
        
        return data
        
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Error loading data: {e}")
        return {
            'groups': {},
            'expenses': {},
            'next_group_id': 1,
            'next_expense_id': 1,
            'recent_members': []
        }

def save_data(data):
    """Save data to file with error handling"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def get_next_group_id():
    data = load_data()
    next_id = data['next_group_id']
    data['next_group_id'] += 1
    if save_data(data):
        return next_id
    return None

def get_next_expense_id():
    data = load_data()
    
    # Find the maximum existing expense ID
    existing_ids = []
    for exp_id in data.get('expenses', {}).keys():
        try:
            existing_ids.append(int(exp_id))
        except (ValueError, TypeError):
            continue
    
    # If no expenses exist, start from 1, else use max + 1
    if existing_ids:
        next_id = max(existing_ids) + 1
    else:
        next_id = 1
    
    # Update the next_expense_id counter
    data['next_expense_id'] = next_id + 1
    
    if save_data(data):
        return next_id
    return None

def update_recent_members(members_list):
    data = load_data()
    recent_members = data.get('recent_members', [])
    
    for member in members_list:
        member_clean = member.strip()
        if member_clean and member_clean not in recent_members:
            # Remove if already exists to avoid duplicates
            if member_clean in recent_members:
                recent_members.remove(member_clean)
            recent_members.insert(0, member_clean)
    
    # Keep only last 10 recent members
    data['recent_members'] = recent_members[:10]
    save_data(data)

def calculate_total_amount(base_amount, discount_amount=0, service_tax_amount=0, gst_amount=0):
    """Calculate total amount with fixed discount, tax, and GST amounts"""
    try:
        base_amount = float(base_amount)
        discount_amount = float(discount_amount)
        service_tax_amount = float(service_tax_amount)
        gst_amount = float(gst_amount)
        
        # Validate inputs
        if base_amount < 0 or discount_amount < 0 or service_tax_amount < 0 or gst_amount < 0:
            return None
        
        # Calculate amount after discount
        amount_after_discount = base_amount - discount_amount
        
        # Ensure amount after discount doesn't go negative
        if amount_after_discount < 0:
            amount_after_discount = 0
        
        # Total amount: Base - Discount + Service Tax + GST
        total_amount = amount_after_discount + service_tax_amount + gst_amount
        
        return {
            'base_amount': round(base_amount, 2),
            'discount_amount': round(discount_amount, 2),
            'amount_after_discount': round(amount_after_discount, 2),
            'service_tax_amount': round(service_tax_amount, 2),
            'gst_amount': round(gst_amount, 2),
            'total_amount': round(total_amount, 2)
        }
    except (ValueError, TypeError):
        return None

def simplify_debts(balances):
    """Simplify debts using minimum transactions"""
    try:
        creditors = []
        debtors = []
        
        # Separate creditors and debtors
        for member, balance in balances.items():
            if balance > 0.01:  # Creditors (using epsilon for float comparison)
                creditors.append((member, balance))
            elif balance < -0.01:  # Debtors
                debtors.append((member, -balance))
        
        settlements = []
        
        # Sort by amount (largest first for better optimization)
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)
        
        # Settle debts
        while creditors and debtors:
            creditor, credit_amt = creditors[0]
            debtor, debt_amt = debtors[0]
            
            settlement_amt = min(credit_amt, debt_amt)
            
            settlements.append({
                'from': debtor,
                'to': creditor,
                'amount': round(settlement_amt, 2)
            })
            
            # Update amounts
            if credit_amt > debt_amt:
                creditors[0] = (creditor, credit_amt - debt_amt)
                debtors.pop(0)
            elif debt_amt > credit_amt:
                debtors[0] = (debtor, debt_amt - credit_amt)
                creditors.pop(0)
            else:
                creditors.pop(0)
                debtors.pop(0)
        
        return settlements
    except Exception:
        return []

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        remember_me = 'remember_me' in request.form
        
        users_data = load_users()
        user = users_data['users'].get(email)
        
        if user and verify_password(user['password'], password):
            if not user.get('verified', False):
                flash('Please verify your email before logging in.', 'warning')
                return redirect(url_for('login'))
            
            session['user_id'] = user['id']
            session['user_email'] = email
            session['user_name'] = user['username']
            
            if remember_me:
                session.permanent = True
            else:
                session.permanent = False
            
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        print(f"Registration attempt: {username}, {email}")  # Debug log
        
        # Validation
        if not all([username, email, password]):
            flash('Please fill in all fields.', 'error')
            return redirect(url_for('login'))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('login'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('login'))
        
        users_data = load_users()
        
        if email in users_data['users']:
            flash('Email already registered. Please login instead.', 'error')
            return redirect(url_for('login'))
        
        # Create user
        user_id = str(uuid.uuid4())
        verification_token = secrets.token_urlsafe(32)
        
        user_data = {
            'id': user_id,
            'username': username,
            'email': email,
            'password': hash_password(password),
            'verified': False,
            'verification_token': verification_token,
            'created_at': datetime.now().isoformat(),
            'profile_visibility': 'private'
        }
        
        users_data['users'][email] = user_data
        
        if save_users(users_data):
            # Send verification email
            if send_verification_email(email, verification_token, username):
                flash('Registration successful! Please check your email to verify your account.', 'success')
            else:
                # If email fails, still create account but warn user
                flash('Registration successful! But we could not send verification email. Please contact support to verify your account.', 'warning')
            return redirect(url_for('login'))
        else:
            flash('Error creating account. Please try again.', 'error')
            return redirect(url_for('login'))
    
    return redirect(url_for('login'))

@app.route('/verify_email/<token>')
def verify_email(token):
    users_data = load_users()
    user_found = False
    
    for email, user in users_data['users'].items():
        if user.get('verification_token') == token:
            user['verified'] = True
            user.pop('verification_token', None)
            user_found = True
            break
    
    if user_found:
        if save_users(users_data):
            flash('Email verified successfully! You can now login.', 'success')
        else:
            flash('Error verifying email. Please try again.', 'error')
    else:
        flash('Invalid or expired verification link.', 'error')
    
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        
        users_data = load_users()
        user = users_data['users'].get(email)
        
        if user and user.get('verified', False):
            reset_token = secrets.token_urlsafe(32)
            user['reset_token'] = reset_token
            user['reset_token_expiry'] = (datetime.now() + timedelta(hours=1)).isoformat()
            
            if save_users(users_data):
                if send_password_reset_email(email, reset_token, user['username']):
                    flash('Password reset instructions sent to your email.', 'success')
                else:
                    flash('Error sending reset email. Please try again.', 'error')
            else:
                flash('Error processing request. Please try again.', 'error')
        else:
            # Don't reveal if email exists for security
            flash('If this email exists and is verified, reset instructions will be sent.', 'success')
        
        return redirect(url_for('login'))
    
    return redirect(url_for('login'))

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    users_data = load_users()
    
    # Find user with valid reset token
    user = None
    user_email = None
    for email, user_data in users_data['users'].items():
        if (user_data.get('reset_token') == token and 
            user_data.get('reset_token_expiry') and 
            datetime.fromisoformat(user_data['reset_token_expiry']) > datetime.now()):
            user = user_data
            user_email = email
            break
    
    if not user:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('reset_password', token=token))
        
        user['password'] = hash_password(password)
        user.pop('reset_token', None)
        user.pop('reset_token_expiry', None)
        
        if save_users(users_data):
            flash('Password reset successfully! You can now login with your new password.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error resetting password. Please try again.', 'error')
    
    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

# Update index route to require login
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        groups = []
        
        # Only show groups that belong to the current user or are shared with them
        user_groups = []
        for group_id, group in data.get('groups', {}).items():
            if isinstance(group, dict):
                # Check if user owns this group or has access
                if group.get('owner_id') == session['user_id'] or session['user_id'] in group.get('shared_with', []):
                    if 'id' not in group:
                        group['id'] = int(group_id) if group_id.isdigit() else 0
                    if 'members' not in group:
                        group['members'] = []
                    if 'created_at' not in group:
                        group['created_at'] = datetime.now().isoformat()
                    if 'expenses' not in group:
                        group['expenses'] = []
                    user_groups.append(group)
        
        # Sort groups by creation date (newest first)
        user_groups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Calculate stats for homepage
        total_groups = len(user_groups)
        total_expenses = len(data.get('expenses', {}))
        total_spent = sum(expense.get('amount', 0) for expense in data.get('expenses', {}).values())
        
        return render_template('index.html', 
                             groups=user_groups, 
                             total_groups=total_groups,
                             total_expenses=total_expenses,
                             total_spent=total_spent,
                             user_name=session.get('user_name', 'Friend'))
    except Exception as e:
        print(f"Error in index route: {e}")
        flash('Error loading data. Please try again.', 'error')
        return render_template('index.html', groups=[], total_groups=0, total_expenses=0, total_spent=0, user_name=session.get('user_name', 'Friend'))

# ... (Keep all your other routes as before)

# Debug route to check email configuration
@app.route('/debug/email')
def debug_email():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    email_config = {
        'MAIL_SERVER': app.config['MAIL_SERVER'],
        'MAIL_PORT': app.config['MAIL_PORT'],
        'MAIL_USERNAME_set': bool(app.config['MAIL_USERNAME']),
        'MAIL_PASSWORD_set': bool(app.config['MAIL_PASSWORD']),
        'MAIL_USE_TLS': app.config['MAIL_USE_TLS']
    }
    
    return jsonify(email_config)

# Debug route to check users
@app.route('/debug/users')
def debug_users():
    users_data = load_users()
    return jsonify({
        'total_users': len(users_data.get('users', {})),
        'users': list(users_data.get('users', {}).keys())
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Initialize data files on startup
    load_data()
    load_users()
    app.run(host='0.0.0.0', port=port, debug=True)