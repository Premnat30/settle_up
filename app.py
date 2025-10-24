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
            if 'recent_members' not in data:
                data['recent_members'] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default structure if file doesn't exist or is corrupted
        return {'groups': {}, 'expenses': {}, 'next_group_id': 1, 'next_expense_id': 1, 'recent_members': []}

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

def update_recent_members(members_list):
    data = load_data()
    recent_members = data.get('recent_members', [])
    
    for member in members_list:
        if member in recent_members:
            recent_members.remove(member)
        recent_members.insert(0, member)
    
    # Keep only last 20 recent members
    data['recent_members'] = recent_members[:20]
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
    except ValueError:
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
            
            # Update recent members
            update_recent_members(member_names)
            
            if save_data(data):
                flash(f'Group "{group_name}" created successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error saving group. Please try again.', 'error')
                return redirect(url_for('create_group'))
                
        except Exception as e:
            flash(f'Error creating group: {str(e)}', 'error')
            return redirect(url_for('create_group'))
    
    # Load recent members for suggestions
    data = load_data()
    recent_members = data.get('recent_members', [])
    return render_template('create_group.html', recent_members=recent_members)

@app.route('/api/recent_members')
def get_recent_members():
    data = load_data()
    recent_members = data.get('recent_members', [])
    return jsonify(recent_members)

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
                    expense['visit_date_display'] = expense.get('visit_date', expense.get('date', ''))[:10]
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
            amount_calculation = calculate_total_amount(base_amount, discount_percent, service_tax_percent, gst_percent)
            if not amount_calculation:
                flash('Error calculating total amount', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            total_amount = amount_calculation['total_amount']
            
            expense_id = get_next_expense_id()
            if expense_id is None:
                flash('Error creating expense. Please try again.', 'error')
                return redirect(url_for('add_expense', group_id=group_id))
            
            expense = {
                'id': expense_id,
                'description': description,
                'base_amount': base_amount,
                'discount_percent': discount_percent,
                'service_tax_percent': service_tax_percent,
                'gst_percent': gst_percent,
                'amount_calculation': amount_calculation,
                'amount': total_amount,
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
                    try:
                        share_amount = float(request.form.get(f'share_{member}', 0))
                    except ValueError:
                        share_amount = 0
                    expense['shares'][member] = share_amount
                    total_custom += share_amount
                
                # Validate custom split totals
                if abs(total_custom - total_amount) > 0.01:
                    flash(f'Custom shares (${total_custom:.2f}) must equal total amount (${total_amount:.2f})', 'error')
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

@app.route('/group/<int:group_id>/expense/<int:expense_id>/edit', methods=['GET', 'POST'])
def edit_expense(group_id, expense_id):
    try:
        data = load_data()
        group = data['groups'].get(str(group_id))
        expense = data['expenses'].get(str(expense_id))
        
        if not group or not expense or expense['group_id'] != group_id:
            flash('Expense not found', 'error')
            return redirect(url_for('group_detail', group_id=group_id))
        
        if request.method == 'POST':
            description = request.form['description'].strip()
            try:
                base_amount = float(request.form['base_amount'])
                discount_percent = float(request.form.get('discount_percent', 0))
                service_tax_percent = float(request.form.get('service_tax_percent', 0))
                gst_percent = float(request.form.get('gst_percent', 0))
                visit_date = request.form.get('visit_date', '')
            except ValueError:
                flash('Please enter valid numbers for amounts', 'error')
                return redirect(url_for('edit_expense', group_id=group_id, expense_id=expense_id))
            
            paid_by = request.form['paid_by']
            split_type = request.form['split_type']
            
            if not description:
                flash('Please enter a description', 'error')
                return redirect(url_for('edit_expense', group_id=group_id, expense_id=expense_id))
            
            if base_amount <= 0:
                flash('Base amount must be greater than 0', 'error')
                return redirect(url_for('edit_expense', group_id=group_id, expense_id=expense_id))
            
            # Calculate total amount with taxes
            amount_calculation = calculate_total_amount(base_amount, discount_percent, service_tax_percent, gst_percent)
            if not amount_calculation:
                flash('Error calculating total amount', 'error')
                return redirect(url_for('edit_expense', group_id=group_id, expense_id=expense_id))
            
            total_amount = amount_calculation['total_amount']
            
            # Update expense
            expense.update({
                'description': description,
                'base_amount': base_amount,
                'discount_percent': discount_percent,
                'service_tax_percent': service_tax_percent,
                'gst_percent': gst_percent,
                'amount_calculation': amount_calculation,
                'amount': total_amount,
                'paid_by': paid_by,
                'split_type': split_type,
                'visit_date': visit_date
            })
            
            # Update shares if split type changed
            if split_type == 'equal':
                share_amount = round(total_amount / len(group['members']), 2)
                expense['shares'] = {member: share_amount for member in group['members']}
            else:
                # Keep existing shares for custom split
                pass
            
            if save_data(data):
                flash('Expense updated successfully!', 'success')
                return redirect(url_for('group_detail', group_id=group_id))
            else:
                flash('Error updating expense', 'error')
        
        return render_template('edit_expense.html', group=group, expense=expense)
    except Exception as e:
        flash(f'Error editing expense: {str(e)}', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

@app.route('/group/<int:group_id>/expense/<int:expense_id>/delete', methods=['POST'])
def delete_expense(group_id, expense_id):
    try:
        data = load_data()
        expense_key = str(expense_id)
        
        if expense_key in data['expenses'] and data['expenses'][expense_key]['group_id'] == group_id:
            # Remove expense from group's expense list
            group = data['groups'].get(str(group_id))
            if group and 'expenses' in group:
                group['expenses'] = [exp_id for exp_id in group['expenses'] if exp_id != expense_id]
            
            # Delete the expense
            del data['expenses'][expense_key]
            
            if save_data(data):
                flash('Expense deleted successfully!', 'success')
            else:
                flash('Error deleting expense', 'error')
        else:
            flash('Expense not found', 'error')
        
        return redirect(url_for('group_detail', group_id=group_id))
    except Exception as e:
        flash('Error deleting expense', 'error')
        return redirect(url_for('group_detail', group_id=group_id))

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
        for exp_id, expense in data['expenses'].items():
            if expense['group_id'] == group_id:
                group_expenses.append(expense)
        
        # Sort expenses by date
        group_expenses.sort(key=lambda x: x.get('date', ''))
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['SettleUp - Expense Report'])
        writer.writerow([f'Group: {group["name"]}'])
        writer.writerow([f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}'])
        writer.writerow([])
        
        # Write expenses
        writer.writerow(['Date', 'Visit Date', 'Description', 'Paid By', 'Base Amount', 'Discount', 'Service Tax', 'GST', 'Total Amount', 'Split Type'])
        
        for expense in group_expenses:
            visit_date = expense.get('visit_date', expense.get('date', '')[:10])
            writer.writerow([
                expense.get('date', '')[:10],
                visit_date,
                expense['description'],
                expense['paid_by'],
                f"${expense.get('base_amount', 0):.2f}",
                f"{expense.get('discount_percent', 0)}%",
                f"{expense.get('service_tax_percent', 0)}%",
                f"{expense.get('gst_percent', 0)}%",
                f"${expense['amount']:.2f}",
                expense['split_type'].title()
            ])
        
        # Prepare response
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=settleup_{group['name']}_{datetime.now().strftime('%Y%m%d')}.csv"}
        )
    except Exception as e:
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

# ... (keep the existing settle_up, delete_group, and other routes from previous version)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
