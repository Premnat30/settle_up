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
            data = json.load(f)
            # Ensure all required keys exist
            if 'groups' not in data:
                data['groups'] = {}
            if 'expenses' not in data:
                data['expenses'] = {}
            if 'next_group_id' not in data:
                data['next_group_id'] = 1
            if 'next_expense_id' not in data:
                data['next_expense_id'] = 1
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default structure if file doesn't exist or is corrupted
        return {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1}

def save_data(data):
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
    next_id = data['next_expense_id']
    data['next_expense_id'] += 1
    if save_data(data):
        return next_id
    return None

# Routes
@app.route('/')
def index():
    try:
        data = load_data()
        groups = list(data['groups'].values())
        # Sort groups by creation date (newest first)
        groups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Calculate stats for homepage
        total_groups = len(groups)
        total_expenses = len(data['expenses'])
        total_spent = sum(expense['amount'] for expense in data['expenses'].values())
        
        return render_template('index.html', 
                             groups=groups, 
                             total_groups=total_groups,
                             total_expenses=total_expenses,
                             total_spent=total_spent)
    except Exception as e:
        flash('Error loading data. Please try again.', 'error')
        return render_template('index.html', groups=[], total_groups=0, total_expenses=0, total_spent=0)

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
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
                'created_at': datetime.now().isoformat(),
                'expenses': []
            }
            
            data['groups'][str(group_id)] = group
            if save_data(data):
                flash(f'Group "{group_name}" created successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error saving group. Please try again.', 'error')
                return redirect(url_for('create_group'))
                
        except Exception as e:
            flash(f'Error creating group: {str(e)}', 'error')
            return redirect(url_for('create_group'))
    
    return render_template('create_group.html')

@app.route('/group/<int:group_id>')
def group_detail(group_id):
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Get expenses for this group
        group_expenses = []
        for exp_id, expense in data['expenses'].items():
            if expense['group_id'] == group_id:
                try:
                    expense['date_display'] = datetime.fromisoformat(expense['date']).strftime('%Y-%m-%d %H:%M')
                    group_expenses.append(expense)
                except (ValueError, KeyError):
                    continue
        
        # Sort expenses by date (newest first)
        group_expenses.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Calculate total spent
        total_spent = sum(expense.get('amount', 0) for expense in group_expenses)
        
        return render_template('group_detail.html', 
                             group=group, 
                             expenses=group_expenses,
                             total_spent=total_spent)
    except Exception as e:
        flash('Error loading group details', 'error')
        return redirect(url_for('index'))

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
            try:
                amount = float(request.form['amount'])
            except ValueError:
                flash('Please enter a valid amount', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            paid_by = request.form['paid_by']
            split_type = request.form['split_type']
            
            if not description:
                flash('Please enter a description', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            if amount <= 0:
                flash('Amount must be greater than 0', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            expense_id = get_next_expense_id()
            if expense_id is None:
                flash('Error creating expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            expense = {
                'id': expense_id,
                'description': description,
                'amount': amount,
                'paid_by': paid_by,
                'group_id': group_id,
                'split_type': split_type,
                'date': datetime.now().isoformat(),
                'shares': {}
            }
            
            # Calculate shares
            if split_type == 'equal':
                share_amount = round(amount / len(group['members']), 2)
                for member in group['members']:
                    expense['shares'][member] = share_amount
            else:
                # Custom split
                total_custom = 0
                for member in group['members']:
                    try:
                        share_amount = float(request.form.get(f'share_{member}', 0))
                    except ValueError:
                        share_amount = 0
                    expense['shares'][member] = share_amount
                    total_custom += share_amount
                
                # Validate custom split totals
                if abs(total_custom - amount) > 0.01:
                    flash(f'Custom shares (${total_custom:.2f}) must equal total amount (${amount:.2f})', 'error')
                    return redirect(url_for('add_expense', group_id=group_id))
            
            data['expenses'][str(expense_id)] = expense
            if str(group_id) in data['groups']:
                if 'expenses' not in data['groups'][str(group_id)]:
                    data['groups'][str(group_id)]['expenses'] = []
                data['groups'][str(group_id)]['expenses'].append(expense_id)
            
            if save_data(data):
                flash('Expense added successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error saving expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
        
        return render_template('add_expense.html', group=group)
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/group/<int:group_id>/settle')
def settle_up(group_id):
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Calculate balances for each member
        balances = {member: 0.0 for member in group['members']}
        
        # Get all expenses for this group
        group_expenses = []
        for exp_id in group.get('expenses', []):
            expense = data['expenses'].get(str(exp_id))
            if expense and expense['group_id'] == group_id:
                group_expenses.append(expense)
        
        # Calculate net balance for each member
        for expense in group_expenses:
            # The payer gets positive amount (they are owed money)
            balances[expense['paid_by']] += expense['amount']
            
            # Participants get negative amounts (they owe money)
            for member, share in expense['shares'].items():
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
        flash('Error calculating settlements', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/group/<int:group_id>/delete', methods=['POST'])
def delete_group(group_id):
    try:
        data = load_data()
        group_key = str(group_id)
        
        if group_key in data['groups']:
            group_name = data['groups'][group_key]['name']
            
            # Remove all expenses for this group
            expenses_to_delete = []
            for exp_id, expense in data['expenses'].items():
                if expense['group_id'] == group_id:
                    expenses_to_delete.append(exp_id)
            
            for exp_id in expenses_to_delete:
                del data['expenses'][exp_id]
            
            # Remove the group
            del data['groups'][group_key]
            
            if save_data(data):
                flash(f'Group "{group_name}" deleted successfully!', 'success')
            else:
                flash('Error deleting group', 'error')
        else:
            flash('Group not found', 'error')
        
        return redirect(url_for('index'))
    except Exception as e:
        flash('Error deleting group', 'error')
        return redirect(url_for('index'))

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

@app.route('/clear_data')
def clear_data():
    """Route to clear all data (for testing)"""
    try:
        data = {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1}
        if save_data(data):
            flash('All data cleared!', 'success')
        else:
            flash('Error clearing data', 'error')
    except Exception:
        flash('Error clearing data', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
