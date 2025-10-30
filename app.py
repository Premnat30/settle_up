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
import re
import threading
import time


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

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

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

def send_verification_email_safe(email, verification_token, username):
    """Safe email function that doesn't cause timeouts"""
    try:
        # Just print the verification link for now
        verification_link = f"https://settle-up-app.onrender.com/verify_email/{verification_token}"
        print(f"📧 VERIFICATION LINK for {username} ({email}): {verification_link}")
        print(f"💡 Email functionality temporarily disabled to prevent timeouts")
        
        # Return success but don't actually send email
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


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
        
        print(f"Registration attempt: {username}, {email}")
        
        # Quick validation
        if not all([username, email, password]):
            flash('Please fill in all fields.', 'error')
            return render_template('login.html', registration_error=True)
        
        # Validate email format
        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return render_template('login.html', registration_error=True)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('login.html', registration_error=True)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('login.html', registration_error=True)
        
        users_data = load_users()
        
        if email in users_data['users']:
            flash('Email already registered. Please login instead.', 'error')
            return render_template('login.html', registration_error=True)
        
        # Create user
        user_id = str(uuid.uuid4())
        verification_token = secrets.token_urlsafe(32)
        
        user_data = {
            'id': user_id,
            'username': username,
            'email': email,
            'password': hash_password(password),
            'verified': True,  # Auto-verify for now to bypass email
            'verification_token': verification_token,
            'created_at': datetime.now().isoformat(),
            'profile_visibility': 'private'
        }
        
        users_data['users'][email] = user_data
        
        if save_users(users_data):
            # Safe email call - just prints to logs
            send_verification_email_safe(email, verification_token, username)
            
            flash('Registration successful! You can now login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error creating account. Please try again.', 'error')
            return render_template('login.html', registration_error=True)
    
    return redirect(url_for('login'))

@app.route('/verify_email/<token>')
def verify_email(token):
    """Verify email with the token"""
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

@app.route('/debug/users')
def debug_users():
    """Show all users for debugging"""
    users_data = load_users()
    user_list = []
    
    for email, user in users_data.get('users', {}).items():
        user_list.append({
            'email': email,
            'username': user.get('username'),
            'verified': user.get('verified', False),
            'has_token': 'verification_token' in user
        })
    
    return jsonify({
        'total_users': len(user_list),
        'users': user_list
    })

@app.route('/auto_verify_all')
def auto_verify_all():
    """Auto-verify all existing users"""
    users_data = load_users()
    verified_count = 0
    
    for email, user in users_data['users'].items():
        if not user.get('verified', False):
            user['verified'] = True
            verified_count += 1
    
    if save_users(users_data):
        flash(f'Successfully verified {verified_count} users!', 'success')
    else:
        flash('Error verifying users', 'error')
    
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        
        # Validate email format
        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('login'))
        
        users_data = load_users()
        user = users_data['users'].get(email)
        
        if user and user.get('verified', False):
            reset_token = secrets.token_urlsafe(32)
            user['reset_token'] = reset_token
            user['reset_token_expiry'] = (datetime.now() + timedelta(hours=1)).isoformat()
            
            if save_users(users_data):
                try:
                    if send_password_reset_email(email, reset_token, user['username']):
                        flash('Password reset instructions sent to your email.', 'success')
                    else:
                        flash('Error sending reset email. Please try again.', 'error')
                except Exception as e:
                    print(f"Error in password reset email: {e}")
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
        # Make sure we pass all required variables even in error case
        return render_template('index.html', 
                             groups=[], 
                             total_groups=0, 
                             total_expenses=0, 
                             total_spent=0, 
                             user_name=session.get('user_name', 'Friend'))
    
    # === ADD MISSING GROUP MANAGEMENT ROUTES ===

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            group_name = request.form['group_name'].strip()
            member_names = [name.strip() for name in request.form['members'].split(',') if name.strip()]
            
            if not group_name:
                flash('Please enter a group name', 'error')
                return redirect(url_for('create_group'))
            
            if len(member_names) < 2:
                flash('Please add at least 2 members', 'error')
                return redirect(url_for('create_group'))
            
            group_id = get_next_group_id()
            if group_id is None:
                flash('Error creating group. Please try again.', 'error')
                return redirect(url_for('create_group'))
            
            data = load_data()
            
            group = {
                'id': group_id,
                'name': group_name,
                'members': member_names,
                'owner_id': session['user_id'],
                'owner_email': session['user_email'],
                'shared_with': [],
                'share_token': secrets.token_urlsafe(16),
                'created_at': datetime.now().isoformat(),
                'expenses': []
            }
            
            data['groups'][str(group_id)] = group
            
            # Update recent members
            update_recent_members(member_names)
            
            if save_data(data):
                flash(f'Group "{group_name}" created successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error saving group. Please try again.', 'error')
                return redirect(url_for('create_group'))
                
        except Exception as e:
            print(f"Error creating group: {e}")
            flash(f'Error creating group: Please try again.', 'error')
            return redirect(url_for('create_group'))
    
    # Load recent members for suggestions
    try:
        data = load_data()
        recent_members = data.get('recent_members', [])
    except:
        recent_members = []
    
    return render_template('create_group.html', recent_members=recent_members)

@app.route('/group/<int:group_id>')
def group_detail(group_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        group_key = str(group_id)
        group = data['groups'].get(group_key)
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Check if user has access to this group
        if (group.get('owner_id') != session['user_id'] and 
            session['user_id'] not in group.get('shared_with', [])):
            flash('You do not have access to this group.', 'error')
            return redirect(url_for('index'))
        
        # Ensure group has all required fields
        if 'id' not in group:
            group['id'] = group_id
        if 'members' not in group:
            group['members'] = []
        if 'expenses' not in group:
            group['expenses'] = []
        if 'created_at' not in group:
            group['created_at'] = datetime.now().isoformat()
        
        # Get expenses for this group
        group_expenses = []
        
        for exp_id in group.get('expenses', []):
            # Try both string and integer keys
            expense_key_str = str(exp_id)
            expense_key_int = exp_id
            
            expense = None
            if expense_key_str in data.get('expenses', {}):
                expense = data['expenses'][expense_key_str]
            elif isinstance(expense_key_int, int) and str(expense_key_int) in data.get('expenses', {}):
                expense = data['expenses'][str(expense_key_int)]
            
            if expense and expense.get('group_id') == group_id:
                try:
                    # Ensure expense has all required fields with safe defaults
                    if 'date' not in expense:
                        expense['date'] = datetime.now().isoformat()
                    if 'visit_date' not in expense:
                        expense['visit_date'] = expense['date'][:10]
                    if 'base_amount' not in expense:
                        expense['base_amount'] = expense.get('amount', 0)
                    if 'discount_amount' not in expense:
                        expense['discount_amount'] = 0
                    if 'service_tax_amount' not in expense:
                        expense['service_tax_amount'] = 0
                    if 'gst_amount' not in expense:
                        expense['gst_amount'] = 0
                    if 'participants' not in expense:
                        expense['participants'] = group['members']
                    
                    # Safe date parsing
                    try:
                        expense['date_display'] = datetime.fromisoformat(expense['date']).strftime('%Y-%m-%d %H:%M')
                    except (ValueError, TypeError):
                        expense['date_display'] = "Unknown date"
                    
                    expense['visit_date_display'] = expense['visit_date'][:10]
                    group_expenses.append(expense)
                except (ValueError, KeyError) as e:
                    print(f"Error processing expense {exp_id}: {e}")
                    continue
        
        # Sort expenses by date (newest first)
        group_expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Calculate total spent
        total_spent = sum(expense.get('amount', 0) for expense in group_expenses)
        
        return render_template('group_detail.html', 
                             group=group, 
                             expenses=group_expenses,
                             total_spent=total_spent,
                             user_name=session.get('user_name'))
    except Exception as e:
        print(f"Error in group_detail: {e}")
        flash('Error loading group details. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
def add_expense(group_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        group_key = str(group_id)
        group = data['groups'].get(group_key)
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Check if user has access to this group
        if (group.get('owner_id') != session['user_id'] and 
            session['user_id'] not in group.get('shared_with', [])):
            flash('You do not have access to this group.', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            description = request.form['description'].strip()
            
            # Get tax calculation fields as FIXED AMOUNTS
            try:
                base_amount = float(request.form['base_amount'])
                discount_amount = float(request.form.get('discount_amount', 0))
                service_tax_amount = float(request.form.get('service_tax_amount', 0))
                gst_amount = float(request.form.get('gst_amount', 0))
                visit_date = request.form.get('visit_date', '')
            except ValueError:
                flash('Please enter valid numbers for amounts', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            paid_by = request.form['paid_by']
            split_type = request.form['split_type']
            
            # Get selected participants
            participants = request.form.getlist('participants')
            if not participants:
                flash('Please select at least one participant', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            if not description:
                flash('Please enter a description', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            if base_amount <= 0:
                flash('Base amount must be greater than 0', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            # Calculate total amount with FIXED amounts (no percentage calculations)
            amount_after_discount = base_amount - discount_amount
            total_amount = amount_after_discount + service_tax_amount + gst_amount
            
            # Get a new expense ID
            expense_id = get_next_expense_id()
            if expense_id is None:
                flash('Error creating expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            # Create the expense object with FIXED amounts
            expense = {
                'id': expense_id,
                'description': description,
                'base_amount': base_amount,
                'discount_amount': discount_amount,
                'service_tax_amount': service_tax_amount,
                'gst_amount': gst_amount,
                'amount': round(total_amount, 2),
                'paid_by': paid_by,
                'group_id': group_id,
                'split_type': split_type,
                'visit_date': visit_date,
                'participants': participants,
                'date': datetime.now().isoformat(),
                'shares': {}
            }
            
            # Calculate shares - ONLY for selected participants
            if split_type == 'equal':
                share_amount = round(total_amount / len(participants), 2)
                for member in group['members']:
                    if member in participants:
                        expense['shares'][member] = share_amount
                    else:
                        expense['shares'][member] = 0
            else:
                # Custom split - only for selected participants
                total_custom = 0
                for member in group['members']:
                    if member in participants:
                        share_amount = float(request.form.get(f'share_{member}', 0))
                        expense['shares'][member] = share_amount
                        total_custom += share_amount
                    else:
                        expense['shares'][member] = 0
                
                # Validate custom split totals
                if abs(total_custom - total_amount) > 0.01:
                    flash(f'Custom shares (${total_custom:.2f}) must equal total amount (${total_amount:.2f})', 'error')
                    return redirect(url_for('add_expense', group_id=group_id))
            
            # Save the expense with string key
            expense_key = str(expense_id)
            data['expenses'][expense_key] = expense
            
            # Add expense ID to group's expense list (ensure it's a list)
            if 'expenses' not in group:
                group['expenses'] = []
            
            # Add the new expense ID if it doesn't exist
            if expense_id not in group['expenses']:
                group['expenses'].append(expense_id)
            
            if save_data(data):
                flash('Expense added successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error saving expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
        
        # Pass today's date for the form
        today = datetime.now().strftime('%Y-%m-%d')
        return render_template('add_expense.html', group=group, today=today)
        
    except Exception as e:
        print(f"Error in add_expense: {e}")
        flash(f'Error: Please try again.', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/group/<int:group_id>/settle')
def settle_up(group_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Ensure group has required fields
        if 'members' not in group:
            group['members'] = []
        
        # Calculate balances for each member
        balances = {member: 0.0 for member in group['members']}
        
        # Get all expenses for this group
        group_expenses = []
        for exp_id in group.get('expenses', []):
            expense = data.get('expenses', {}).get(str(exp_id))
            if expense and expense.get('group_id') == group_id:
                group_expenses.append(expense)
        
        # Calculate net balance for each member
        for expense in group_expenses:
            # The payer gets positive amount (they are owed money)
            payer = expense.get('paid_by')
            if payer in balances:
                balances[payer] += expense.get('amount', 0)
            
            # Participants get negative amounts (they owe money)
            for member, share in expense.get('shares', {}).items():
                if member in balances:
                    balances[member] -= share
        
        # Round balances to avoid floating point issues
        balances = {member: round(balance, 2) for member, balance in balances.items()}
        
        # Simplify debts
        settlements = simplify_debts(balances)
        
        return render_template('settle_up.html', 
                             group=group, 
                             settlements=settlements, 
                             balances=balances,
                             total_expenses=len(group_expenses))
    except Exception as e:
        print(f"Error in settle_up: {e}")
        flash('Error calculating settlements', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/group/<int:group_id>/share')
def share_group(group_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Check if user owns the group
        if group.get('owner_id') != session['user_id']:
            flash('You can only share groups you own.', 'error')
            return redirect(url_for('group_detail', group_id=group_id))
        
        share_link = f"{request.host_url}join_group/{group['share_token']}"
        
        # Create WhatsApp share link
        whatsapp_text = f"Join my expense sharing group '{group['name']}' on Friendz Share: {share_link}"
        whatsapp_link = f"https://wa.me/?text={whatsapp_text}"
        
        # Create email share content
        email_subject = f"Join my expense sharing group: {group['name']}"
        email_body = f"""
        Hi!

        I've created an expense sharing group "{group['name']}" on Friendz Share and I'd like you to join.

        Click the link below to join the group:
        {share_link}

        With Friendz Share, we can easily track and split expenses together.

        Looking forward to sharing expenses with you!

        Best regards,
        {session['user_name']}
        """
        
        return render_template('share_group.html', 
                             group=group, 
                             share_link=share_link,
                             whatsapp_link=whatsapp_link,
                             email_subject=email_subject,
                             email_body=email_body)
    except Exception as e:
        print(f"Error sharing group: {e}")
        flash('Error generating share link', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/join_group/<token>')
def join_group(token):
    if 'user_id' not in session:
        flash('Please login to join this group.', 'warning')
        return redirect(url_for('login'))
    
    try:
        data = load_data()
        
        # Find group with matching share token
        target_group = None
        for group_id, group in data['groups'].items():
            if group.get('share_token') == token:
                target_group = group
                break
        
        if not target_group:
            flash('Invalid or expired share link.', 'error')
            return redirect(url_for('index'))
        
        # Check if user already has access
        if (target_group.get('owner_id') == session['user_id'] or 
            session['user_id'] in target_group.get('shared_with', [])):
            flash('You already have access to this group.', 'info')
            return redirect(url_for('group_detail', group_id=target_group['id']))
        
        # Add user to shared_with list
        if 'shared_with' not in target_group:
            target_group['shared_with'] = []
        
        target_group['shared_with'].append(session['user_id'])
        
        if save_data(data):
            flash(f'You have joined the group "{target_group["name"]}"!', 'success')
            return redirect(url_for('group_detail', group_id=target_group['id']))
        else:
            flash('Error joining group. Please try again.', 'error')
            return redirect(url_for('index'))
            
    except Exception as e:
        print(f"Error joining group: {e}")
        flash('Error joining group. Please try again.', 'error')
        return redirect(url_for('index'))

# Debug route to check email configuration
@app.route('/debug/email')
def debug_email():
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
    user_list = {}
    for email, user in users_data.get('users', {}).items():
        user_list[email] = {
            'username': user.get('username'),
            'verified': user.get('verified', False),
            'created_at': user.get('created_at')
        }
    
    return jsonify({
        'total_users': len(users_data.get('users', {})),
        'users': user_list
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Initialize data files on startup
    load_data()
    load_users()
    app.run(host='0.0.0.0', port=port, debug=False)