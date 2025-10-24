from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Database configuration for Render
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Handle PostgreSQL URL format for newer versions of SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///settleup.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='group', lazy=True, cascade='all, delete-orphan')

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('group_member.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    split_type = db.Column(db.String(20), default='equal')  # equal, custom
    paid_by = db.relationship('GroupMember')

class ExpenseShare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('group_member.id'), nullable=False)
    share_amount = db.Column(db.Float, nullable=False)
    expense = db.relationship('Expense', backref=db.backref('shares', lazy=True))
    member = db.relationship('GroupMember')

# Routes
@app.route('/')
def index():
    groups = Group.query.all()
    return render_template('index.html', groups=groups)

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if request.method == 'POST':
        group_name = request.form['group_name']
        member_names = [name.strip() for name in request.form['members'].split(',') if name.strip()]
        
        if len(member_names) < 2:
            flash('Please add at least 2 members', 'error')
            return redirect(url_for('create_group'))
        
        group = Group(name=group_name)
        db.session.add(group)
        db.session.commit()
        
        for name in member_names:
            member = GroupMember(name=name, group_id=group.id)
            db.session.add(member)
        
        db.session.commit()
        flash('Group created successfully!', 'success')
        return redirect(url_for('group_detail', group_id=group.id))
    
    return render_template('create_group.html')

@app.route('/group/<int:group_id>')
def group_detail(group_id):
    group = Group.query.get_or_404(group_id)
    expenses = Expense.query.filter_by(group_id=group_id).order_by(Expense.date.desc()).all()
    return render_template('group_detail.html', group=group, expenses=expenses)

@app.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
def add_expense(group_id):
    group = Group.query.get_or_404(group_id)
    
    if request.method == 'POST':
        description = request.form['description']
        amount = float(request.form['amount'])
        paid_by_id = int(request.form['paid_by'])
        split_type = request.form['split_type']
        
        expense = Expense(
            description=description,
            amount=amount,
            paid_by_id=paid_by_id,
            group_id=group_id,
            split_type=split_type
        )
        db.session.add(expense)
        db.session.commit()
        
        # Create expense shares
        if split_type == 'equal':
            share_amount = amount / len(group.members)
            for member in group.members:
                share = ExpenseShare(
                    expense_id=expense.id,
                    member_id=member.id,
                    share_amount=share_amount
                )
                db.session.add(share)
        else:
            # Custom split
            for member in group.members:
                share_amount = float(request.form.get(f'share_{member.id}', 0))
                if share_amount > 0:
                    share = ExpenseShare(
                        expense_id=expense.id,
                        member_id=member.id,
                        share_amount=share_amount
                    )
                    db.session.add(share)
        
        db.session.commit()
        flash('Expense added successfully!', 'success')
        return redirect(url_for('group_detail', group_id=group_id))
    
    return render_template('add_expense.html', group=group)

@app.route('/group/<int:group_id>/settle')
def settle_up(group_id):
    group = Group.query.get_or_404(group_id)
    
    # Calculate balances for each member
    balances = {member.id: 0.0 for member in group.members}
    member_names = {member.id: member.name for member in group.members}
    
    # Calculate net balance for each member
    for expense in group.expenses:
        # The payer gets positive amount (they are owed money)
        balances[expense.paid_by_id] += expense.amount
        
        # Participants get negative amounts (they owe money)
        for share in expense.shares:
            balances[share.member_id] -= share.share_amount
    
    # Simplify debts
    settlements = simplify_debts(balances, member_names)
    
    return render_template('settle_up.html', group=group, settlements=settlements, balances=balances, member_names=member_names)

def simplify_debts(balances, member_names):
    """Simplify debts using minimum transactions"""
    creditors = []
    debtors = []
    
    # Separate creditors and debtors
    for member_id, balance in balances.items():
        if balance > 0.01:  # Creditors (using epsilon for float comparison)
            creditors.append((member_id, balance))
        elif balance < -0.01:  # Debtors
            debtors.append((member_id, -balance))
    
    settlements = []
    
    # Settle debts
    while creditors and debtors:
        creditor_id, credit_amt = creditors[0]
        debtor_id, debt_amt = debtors[0]
        
        settlement_amt = min(credit_amt, debt_amt)
        
        settlements.append({
            'from': member_names[debtor_id],
            'to': member_names[creditor_id],
            'amount': round(settlement_amt, 2)
        })
        
        # Update amounts
        if credit_amt > debt_amt:
            creditors[0] = (creditor_id, credit_amt - debt_amt)
            debtors.pop(0)
        elif debt_amt > credit_amt:
            debtors[0] = (debtor_id, debt_amt - credit_amt)
            creditors.pop(0)
        else:
            creditors.pop(0)
            debtors.pop(0)
    
    return settlements

# API endpoints
@app.route('/api/group/<int:group_id>/balances')
def get_balances(group_id):
    group = Group.query.get_or_404(group_id)
    balances = {member.id: 0.0 for member in group.members}
    member_names = {member.id: member.name for member in group.members}
    
    for expense in group.expenses:
        balances[expense.paid_by_id] += expense.amount
        for share in expense.shares:
            balances[share.member_id] -= share.share_amount
    
    return jsonify({
        'balances': {member_names[k]: round(v, 2) for k, v in balances.items()},
        'settlements': simplify_debts(balances, member_names)
    })

# Initialize database
@app.before_first_request
def create_tables():
    try:
        db.create_all()
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error creating tables: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)