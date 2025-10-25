from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from datetime import datetime
import os
import json
import csv
from io import StringIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')

# Simple file-based storage for persistence
DATA_FILE = 'data.json'

def load_data():
    """Load data from file with proper error handling"""
    try:
        # Create data file if it doesn't exist
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
            
        # Ensure all required keys exist
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
        # Return default structure if file is corrupted
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

def calculate_total_amount(base_amount, discount_percent=0, service_tax_percent=0, gst_percent=0):
    """Calculate total amount after discount, service tax, and GST"""
    try:
        base_amount = float(base_amount)
        discount_percent = float(discount_percent)
        service_tax_percent = float(service_tax_percent)
        gst_percent = float(gst_percent)
        
        # Calculate discount amount
        discount_amount = (base_amount * discount_percent) / 100
        amount_after_discount = base_amount - discount_amount
        
        # Calculate service tax
        service_tax_amount = (amount_after_discount * service_tax_percent) / 100
        
        # Calculate GST
        gst_amount = (amount_after_discount * gst_percent) / 100
        
        # Total amount
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

# Routes
@app.route('/')
def index():
    try:
        data = load_data()
        groups = []
        
        # Safely load groups
        for group_id, group in data.get('groups', {}).items():
            if isinstance(group, dict):
                # Ensure all required fields exist
                if 'id' not in group:
                    group['id'] = int(group_id) if group_id.isdigit() else 0
                if 'members' not in group:
                    group['members'] = []
                if 'created_at' not in group:
                    group['created_at'] = datetime.now().isoformat()
                if 'expenses' not in group:
                    group['expenses'] = []
                groups.append(group)
        
        # Sort groups by creation date (newest first)
        groups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Calculate stats for homepage
        total_groups = len(groups)
        total_expenses = len(data.get('expenses', {}))
        total_spent = sum(expense.get('amount', 0) for expense in data.get('expenses', {}).values())
        
        return render_template('index.html', 
                             groups=groups, 
                             total_groups=total_groups,
                             total_expenses=total_expenses,
                             total_spent=total_spent)
    except Exception as e:
        print(f"Error in index route: {e}")
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

@app.route('/api/recent_members')
def get_recent_members():
    try:
        data = load_data()
        recent_members = data.get('recent_members', [])
        return jsonify(recent_members)
    except:
        return jsonify([])

@app.route('/group/<int:group_id>')
def group_detail(group_id):
    try:
        data = load_data()
        group_key = str(group_id)
        group = data['groups'].get(group_key)
        
        if not group:
            flash('Group not found', 'error')
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
                    if 'discount_percent' not in expense:
                        expense['discount_percent'] = 0
                    if 'service_tax_percent' not in expense:
                        expense['service_tax_percent'] = 0
                    if 'gst_percent' not in expense:
                        expense['gst_percent'] = 0
                    if 'participants' not in expense:
                        expense['participants'] = group['members']  # Default to all members for old expenses
                    
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
                             total_spent=total_spent)
    except Exception as e:
        print(f"Error in group_detail: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading group details. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
def add_expense(group_id):
    try:
        data = load_data()
        group_key = str(group_id)
        group = data['groups'].get(group_key)
        
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
            
            # Calculate total amount with taxes
            discount_amount = (base_amount * discount_percent) / 100
            amount_after_discount = base_amount - discount_amount
            service_tax_amount = (amount_after_discount * service_tax_percent) / 100
            gst_amount = (amount_after_discount * gst_percent) / 100
            total_amount = amount_after_discount + service_tax_amount + gst_amount
            
            # Get a new expense ID
            expense_id = get_next_expense_id()
            if expense_id is None:
                flash('Error creating expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            # Create the expense object
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
                'participants': participants,  # Store who participated
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
                        expense['shares'][member] = 0  # Not participating
            else:
                # Custom split - only for selected participants
                total_custom = 0
                for member in group['members']:
                    if member in participants:
                        share_amount = float(request.form.get(f'share_{member}', 0))
                        expense['shares'][member] = share_amount
                        total_custom += share_amount
                    else:
                        expense['shares'][member] = 0  # Not participating
                
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

@app.route('/group/<int:group_id>/delete', methods=['POST'])
def delete_group(group_id):
    try:
        data = load_data()
        group_key = str(group_id)
        
        if group_key in data.get('groups', {}):
            group_name = data['groups'][group_key].get('name', 'Unknown Group')
            
            # Remove all expenses for this group
            expenses_to_delete = []
            for exp_id, expense in data.get('expenses', {}).items():
                if expense.get('group_id') == group_id:
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
        print(f"Error deleting group: {e}")
        flash('Error deleting group', 'error')
        return redirect(url_for('index'))

@app.route('/group/<int:group_id>/download_csv')
def download_csv(group_id):
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        
        if not group:
            flash('Group not found', 'error')
            return redirect(url_for('index'))
        
        # Get expenses for this group
        group_expenses = []
        for exp_id, expense in data.get('expenses', {}).items():
            if expense.get('group_id') == group_id:
                group_expenses.append(expense)
        
        # Sort expenses by date
        group_expenses.sort(key=lambda x: x.get('date', ''))
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['SettleUp - Expense Report'])
        writer.writerow([f'Group: {group.get("name", "Unknown")}'])
        writer.writerow([f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        
        # Write expenses
        writer.writerow(['Date', 'Visit Date', 'Description', 'Paid By', 'Base Amount', 'Discount', 'Service Tax', 'GST', 'Total Amount', 'Split Type'])
        
        for expense in group_expenses:
            visit_date = expense.get('visit_date', expense.get('date', '')[:10])
            writer.writerow([
                expense.get('date', '')[:10],
                visit_date,
                expense.get('description', ''),
                expense.get('paid_by', ''),
                f"${expense.get('base_amount', 0):.2f}",
                f"{expense.get('discount_percent', 0)}%",
                f"{expense.get('service_tax_percent', 0)}%",
                f"{expense.get('gst_percent', 0)}%",
                f"${expense.get('amount', 0):.2f}",
                expense.get('split_type', 'equal').title()
            ])
        
        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=settleup_{group.get('name', 'group')}_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    except Exception as e:
        print(f"Error generating CSV: {e}")
        flash('Error generating CSV', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/api/calculate_total', methods=['POST'])
def api_calculate_total():
    try:
        data = request.get_json()
        base_amount = float(data.get('base_amount', 0))
        discount_percent = float(data.get('discount_percent', 0))
        service_tax_percent = float(data.get('service_tax_percent', 0))
        gst_percent = float(data.get('gst_percent', 0))
        
        result = calculate_total_amount(base_amount, discount_percent, service_tax_percent, gst_percent)
        
        if result:
            return jsonify({'success': True, 'calculation': result})
        else:
            return jsonify({'success': False, 'error': 'Invalid input'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/clear_data')
def clear_data():
    """Route to clear all data (for testing)"""
    try:
        data = {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1, 'recent_members': []}
        if save_data(data):
            flash('All data cleared!', 'success')
        else:
            flash('Error clearing data', 'error')
    except Exception as e:
        print(f"Error clearing data: {e}")
        flash('Error clearing data', 'error')
    return redirect(url_for('index'))

@app.route('/debug/data')
def debug_data():
    """Debug route to check data structure"""
    try:
        data = load_data()
        return jsonify({
            'groups_count': len(data.get('groups', {})),
            'expenses_count': len(data.get('expenses', {})),
            'next_group_id': data.get('next_group_id'),
            'next_expense_id': data.get('next_expense_id'),
            'recent_members': data.get('recent_members', [])
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/fix_data')
def fix_data():
    """Route to fix data structure issues"""
    try:
        data = load_data()
        
        # Fix expense IDs in groups
        for group_id, group in data.get('groups', {}).items():
            if 'expenses' in group and isinstance(group['expenses'], list):
                # Convert all expense IDs to integers
                fixed_expenses = []
                for exp_id in group['expenses']:
                    try:
                        fixed_expenses.append(int(exp_id))
                    except (ValueError, TypeError):
                        # If it's already an integer, keep it
                        fixed_expenses.append(exp_id)
                group['expenses'] = fixed_expenses
        
        if save_data(data):
            flash('Data structure fixed successfully!', 'success')
        else:
            flash('Error fixing data', 'error')
        
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error fixing data: {e}")
        flash('Error fixing data', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Initialize data file on startup
    load_data()
    app.run(host='0.0.0.0', port=port, debug=False)