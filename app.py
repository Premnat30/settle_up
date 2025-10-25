from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Simple file-based storage for persistence
DATA_FILE = 'data.json'

def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, default=str)

def get_next_group_id():
    data = load_data()
    next_id = data['next_group_id']
    data['next_group_id'] += 1
    save_data(data)
    return next_id

def get_next_expense_id():
    data = load_data()
    next_id = data['next_expense_id']
    data['next_expense_id'] += 1
    save_data(data)
    return next_id

# Routes
@app.route('/')
def index():
    data = load_data()
    groups = list(data['groups'].values())
    # Sort groups by creation date (newest first)
    groups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return render_template('index.html', groups=groups)

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if request.method == 'POST':
        group_name = request.form['group_name']
        member_names = [name.strip() for name in request.form['members'].split(',') if name.strip()]
        
        if len(member_names) < 2:
            flash('Please add at least 2 members', 'error')
            return redirect(url_for('create_group'))
        
        if len(group_name.strip()) == 0:
            flash('Please enter a group name', 'error')
            return redirect(url_for('create_group'))
        
        group_id = get_next_group_id()
        data = load_data()
        
        group = {
            'id': group_id,
            'name': group_name.strip(),
            'members': member_names,
            'created_at': datetime.now().isoformat(),
            'expenses': []
        }
        
        data['groups'][group_id] = group
        save_data(data)
        
        flash(f'Group "{group_name}" created successfully!', 'success')
        return redirect(url_for('group_detail', group_id=group_id))
    
    return render_template('create_group.html')

@app.route('/group/<int:group_id>')
def group_detail(group_id):
    data = load_data()
    group = data['groups'].get(group_id)
    
    if not group:
        flash('Group not found', 'error')
        return redirect(url_for('index'))
    
    # Get expenses for this group
    group_expenses = []
    for exp_id, expense in data['expenses'].items():
        if expense['group_id'] == group_id:
            # Convert date string back to datetime for display
            expense['date_display'] = datetime.fromisoformat(expense['date']).strftime('%Y-%m-%d %H:%M')
            group_expenses.append(expense)
    
    # Sort expenses by date (newest first)
    group_expenses.sort(key=lambda x: x['date'], reverse=True)
    
    # Calculate total spent
    total_spent = sum(expense['amount'] for expense in group_expenses)
    
    return render_template('group_detail.html', 
                         group=group, 
                         expenses=group_expenses,
                         total_spent=total_spent)

@app.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
def add_expense(group_id):
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            description = request.form['description'].strip()
            
            # Get tax calculation fields
            try:
                base_amount = float(request.form['base_amount'])
                discount_percent = float(request.form.get('discount_percent', 0))
                service_tax_percent = float(request.form.get('service_tax_percent', 0))
                gst_percent = float(request.form.get('gst_percent', 0))
                visit_date = request.form.get('visit_date', '')
            except ValueError:
                flash('Please enter valid numbers for amounts', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            paid_by = request.form['paid_by']
            split_type = request.form['split_type']
            
            if not description:
                flash('Please enter a description', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            if base_amount <= 0:
                flash('Base amount must be greater than 0', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            # Calculate total amount with taxes
            discount_amount = (base_amount * discount_percent) / 100
            amount_after_discount = base_amount - discount_amount
            service_tax_amount = (amount_after_discount * service_tax_percent) / 100
            gst_amount = (amount_after_discount * gst_percent) / 100
            total_amount = amount_after_discount + service_tax_amount + gst_amount
            
            expense_id = get_next_expense_id()
            
            expense = {
                'id': expense_id,
                'description': description,
                'base_amount': base_amount,
                'discount_percent': discount_percent,
                'service_tax_percent': service_tax_percent,
                'gst_percent': gst_percent,
                'amount': round(total_amount, 2),
                'paid_by': paid_by,
                'group_id': group_id,
                'split_type': split_type,
                'visit_date': visit_date,
                'date': datetime.now().isoformat(),
                'shares': {}
            }
            
            # Calculate shares
            if split_type == 'equal':
                share_amount = round(total_amount / len(group['members']), 2)
                for member in group['members']:
                    expense['shares'][member] = share_amount
            else:
                # Custom split
                total_custom = 0
                for member in group['members']:
                    share_amount = float(request.form.get(f'share_{member}', 0))
                    expense['shares'][member] = share_amount
                    total_custom += share_amount
                
                # Validate custom split totals
                if abs(total_custom - total_amount) > 0.01:
                    flash(f'Custom shares (${total_custom:.2f}) must equal total amount (${total_amount:.2f})', 'error')
                    return redirect(url_for('add_expense', group_id=group_id))
            
            data['expenses'][str(expense_id)] = expense
            if 'expenses' not in group:
                group['expenses'] = []
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
    data = load_data()
    group = data['groups'].get(group_id)
    
    if not group:
        flash('Group not found', 'error')
        return redirect(url_for('index'))
    
    # Calculate balances for each member
    balances = {member: 0.0 for member in group['members']}
    
    # Get all expenses for this group
    group_expenses = []
    for exp_id in group.get('expenses', []):
        if str(exp_id) in data['expenses']:
            group_expenses.append(data['expenses'][str(exp_id)])
    
    # Calculate net balance for each member
    for expense in group_expenses:
        # The payer gets positive amount (they are owed money)
        balances[expense['paid_by']] += expense['amount']
        
        # Participants get negative amounts (they owe money)
        for member, share in expense['shares'].items():
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

@app.route('/group/<int:group_id>/delete', methods=['POST'])
def delete_group(group_id):
    data = load_data()
    
    if str(group_id) in data['groups']:
        group_name = data['groups'][str(group_id)]['name']
        
        # Remove all expenses for this group
        expenses_to_delete = []
        for exp_id, expense in data['expenses'].items():
            if expense['group_id'] == group_id:
                expenses_to_delete.append(exp_id)
        
        for exp_id in expenses_to_delete:
            del data['expenses'][exp_id]
        
        # Remove the group
        del data['groups'][str(group_id)]
        save_data(data)
        
        flash(f'Group "{group_name}" deleted successfully!', 'success')
    else:
        flash('Group not found', 'error')
    
    return redirect(url_for('index'))

def simplify_debts(balances):
    """Simplify debts using minimum transactions"""
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

# API endpoints
@app.route('/api/group/<int:group_id>/balances')
def get_balances(group_id):
    data = load_data()
    group = data['groups'].get(group_id)
    
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    balances = {member: 0.0 for member in group['members']}
    
    # Get all expenses for this group
    group_expenses = []
    for exp_id in group.get('expenses', []):
        if str(exp_id) in data['expenses']:
            group_expenses.append(data['expenses'][str(exp_id)])
    
    for expense in group_expenses:
        balances[expense['paid_by']] += expense['amount']
        for member, share in expense['shares'].items():
            balances[member] -= share
    
    balances = {member: round(balance, 2) for member, balance in balances.items()}
    
    return jsonify({
        'balances': balances,
        'settlements': simplify_debts(balances)
    })

@app.route('/clear_data')
def clear_data():
    """Route to clear all data (for testing)"""
    data = {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1}
    save_data(data)
    flash('All data cleared!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)