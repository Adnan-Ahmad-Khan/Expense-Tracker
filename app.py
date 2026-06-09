from flask import (
    Flask, render_template, request, redirect,
    url_for, make_response, jsonify, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from datetime import datetime, timedelta
from functools import wraps
import bcrypt
import jwt
import os
import csv
import io
import json

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET'] = os.environ.get(
    'JWT_SECRET', 'your-secret-key-change-in-production')
app.secret_key = os.environ.get(
    'SECRET_KEY', 'flask-secret-change-in-production')

db = SQLAlchemy(app)


# ═══════════════════════════════════════════
#  MODELS
# ═══════════════════════════════════════════

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    monthly_limit = db.Column(db.Float, default=5000)
    currency = db.Column(db.String(10), default='₹')
    theme = db.Column(db.String(10), default='light')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expenses = db.relationship(
        'Expense', backref='user', lazy=True, cascade='all, delete-orphan')
    cat_budgets = db.relationship(
        'CategoryBudget', backref='user', lazy=True, cascade='all, delete-orphan')


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.String(255), default='')
    tags = db.Column(db.String(255), default='')   # comma-separated
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence = db.Column(db.String(20), default='')    # 'weekly' | 'monthly'
    date = db.Column(db.DateTime, default=datetime.utcnow)


class CategoryBudget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    limit = db.Column(db.Float, nullable=False)


with app.app_context():
    db.create_all()


# ═══════════════════════════════════════════
#  JWT HELPERS
# ═══════════════════════════════════════════

def create_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')


def get_current_user():
    token = request.cookies.get('token')
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return User.query.get(payload['user_id'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════
#  AUTH ROUTES
# ═══════════════════════════════════════════

@app.route('/')
def root():
    user = get_current_user()
    if user:
        return redirect(url_for('home'))
    return redirect(url_for('landing'))


@app.route('/landing')
def landing():
    user = get_current_user()
    return render_template('landing.html', user=user)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if get_current_user():
        return redirect(url_for('home'))
    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not name or not email or not password:
            error = 'All fields are required.'
        elif User.query.filter_by(email=email).first():
            error = 'An account with that email already exists.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        else:
            hashed = bcrypt.hashpw(
                password.encode(), bcrypt.gensalt()).decode()
            user = User(name=name, email=email, password=hashed)
            db.session.add(user)
            db.session.commit()
            token = create_token(user.id)
            resp = make_response(redirect(url_for('home')))
            resp.set_cookie('token', token, httponly=True, max_age=7*24*3600)
            return resp
    return render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('home'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
            error = 'Invalid email or password.'
        else:
            token = create_token(user.id)
            resp = make_response(redirect(url_for('home')))
            resp.set_cookie('token', token, httponly=True, max_age=7*24*3600)
            return resp
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('landing')))
    resp.delete_cookie('token')
    return resp


# Switch account = logout then go to login
@app.route('/switch-account')
def switch_account():
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('token')
    return resp


# ═══════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════

CURRENCY_SYMBOLS = {'INR': '₹', 'USD': '$', 'EUR': '€', 'GBP': '£'}


def get_analytics_data(user_id):
    category_data = (
        db.session.query(Expense.category, func.sum(Expense.amount))
        .filter_by(user_id=user_id)
        .group_by(Expense.category)
        .all()
    )
    category_data = [(c, float(t)) for c, t in category_data]

    monthly_data = (
        db.session.query(
            extract('month', Expense.date),
            extract('year',  Expense.date),
            func.sum(Expense.amount),
        )
        .filter_by(user_id=user_id)
        .group_by(extract('month', Expense.date), extract('year', Expense.date))
        .order_by(extract('year', Expense.date), extract('month', Expense.date))
        .all()
    )
    monthly_data = [(f"{int(m)}/{int(y)}", float(t))
                    for m, y, t in monthly_data]

    mom_change = None
    if len(monthly_data) >= 2:
        prev = monthly_data[-2][1]
        curr = monthly_data[-1][1]
        if prev > 0:
            mom_change = round(((curr - prev) / prev) * 100, 1)

    return category_data, monthly_data, mom_change


def generate_insights(user_id, expenses, monthly_data, category_data, monthly_limit):
    """Generate automatic spending insights."""
    insights = []

    if not expenses:
        return insights

    # Total this month
    now = datetime.utcnow()
    this_month = [e for e in expenses if e.date.month ==
                  now.month and e.date.year == now.year]
    last_month = [e for e in expenses if
                  (e.date.month == (now.month - 1)
                   or (now.month == 1 and e.date.month == 12))
                  and e.date.year == (now.year if now.month > 1 else now.year - 1)]

    this_total = sum(e.amount for e in this_month)
    last_total = sum(e.amount for e in last_month)

    # MoM insight
    if last_total > 0 and this_total > 0:
        diff_pct = ((this_total - last_total) / last_total) * 100
        if diff_pct > 20:
            insights.append({
                'icon': '📈',
                'type': 'warning',
                'text': f"You spent {abs(diff_pct):.0f}% more this month compared to last month."
            })
        elif diff_pct < -10:
            insights.append({
                'icon': '📉',
                'type': 'success',
                'text': f"Great job! You spent {abs(diff_pct):.0f}% less this month vs last month."
            })

    # Budget alert
    if monthly_limit > 0 and this_total >= monthly_limit * 0.8:
        pct = (this_total / monthly_limit) * 100
        insights.append({
            'icon': '⚠️',
            'type': 'danger',
            'text': f"You've used {pct:.0f}% of your monthly budget. Consider slowing down spending."
        })

    # Top category this month
    if this_month:
        cat_map = {}
        for e in this_month:
            cat_map[e.category] = cat_map.get(e.category, 0) + e.amount
        top_cat = max(cat_map, key=cat_map.get)
        top_amt = cat_map[top_cat]
        top_pct = (top_amt / this_total * 100) if this_total > 0 else 0
        if top_pct > 40:
            insights.append({
                'icon': '🏷️',
                'type': 'info',
                'text': f"{top_cat} makes up {top_pct:.0f}% of your spending this month ({top_amt:.0f})."
            })

    # Highest spend day of week
    if len(expenses) >= 5:
        day_map = {}
        for e in expenses:
            day = e.date.strftime('%A')
            day_map[day] = day_map.get(day, 0) + e.amount
        top_day = max(day_map, key=day_map.get)
        insights.append({
            'icon': '📅',
            'type': 'info',
            'text': f"You tend to spend the most on {top_day}s."
        })

    # Recurring count
    recurring = [e for e in expenses if e.is_recurring]
    if recurring:
        recurring_total = sum(e.amount for e in recurring)
        insights.append({
            'icon': '🔁',
            'type': 'info',
            'text': f"You have {len(recurring)} recurring expense(s) totalling {recurring_total:.0f}."
        })

    return insights[:4]   # max 4 insights


# ═══════════════════════════════════════════
#  MAIN ROUTES
# ═══════════════════════════════════════════

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def home():
    user = get_current_user()

    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        category = request.form.get('category')
        notes = request.form.get('notes', '')
        tags = request.form.get('tags', '')
        is_recurring = request.form.get('is_recurring') == 'on'
        recurrence = request.form.get('recurrence', '') if is_recurring else ''

        db.session.add(Expense(
            user_id=user.id, amount=amount, category=category,
            notes=notes, tags=tags,
            is_recurring=is_recurring, recurrence=recurrence
        ))
        db.session.commit()

        # Check budget alerts
        alerts = check_budget_alerts(user)
        return redirect(url_for('home', added=1, alerts=json.dumps(alerts)))

    selected_month = request.args.get('month')
    selected_category = request.args.get('category')
    search_query = request.args.get('q', '')
    selected_tag = request.args.get('tag', '')

    query = Expense.query.filter_by(user_id=user.id)

    if selected_category:
        query = query.filter(Expense.category == selected_category)
    if selected_month:
        year, month = selected_month.split('-')
        query = query.filter(
            extract('year',  Expense.date) == int(year),
            extract('month', Expense.date) == int(month),
        )
    if search_query:
        query = query.filter(
            (Expense.category.ilike(f'%{search_query}%')) |
            (Expense.notes.ilike(f'%{search_query}%')) |
            (Expense.tags.ilike(f'%{search_query}%'))
        )
    if selected_tag:
        query = query.filter(Expense.tags.ilike(f'%{selected_tag}%'))

    expenses = query.order_by(Expense.date.desc()).all()
    all_expenses = Expense.query.filter_by(user_id=user.id).all()
    total_spent = sum(e.amount for e in all_expenses)

    category_data, monthly_data, _ = get_analytics_data(user.id)

    # Insights
    insights = generate_insights(
        user.id, all_expenses, monthly_data, category_data, user.monthly_limit)

    categories = [c[0] for c in db.session.query(Expense.category)
                  .filter_by(user_id=user.id).distinct().all()]

    # All unique tags
    all_tags = set()
    for e in all_expenses:
        if e.tags:
            for t in e.tags.split(','):
                t = t.strip()
                if t:
                    all_tags.add(t)

    months = [
        f"{int(y)}-{int(m):02d}"
        for y, m in db.session.query(
            extract('year',  Expense.date),
            extract('month', Expense.date),
        )
        .filter(Expense.user_id == user.id)
        .distinct()
        .order_by(extract('year', Expense.date), extract('month', Expense.date))
        .all()
    ]

    # Budget alerts from query param
    alerts_raw = request.args.get('alerts', '[]')
    try:
        alerts = json.loads(alerts_raw)
    except Exception:
        alerts = []

    return render_template('index.html',
                           user=user,
                           expenses=expenses,
                           total_spent=total_spent,
                           monthly_limit=user.monthly_limit,
                           currency=user.currency,
                           category_data=category_data,
                           monthly_data=monthly_data,
                           categories=categories,
                           months=months,
                           selected_month=selected_month,
                           selected_category=selected_category,
                           search_query=search_query,
                           selected_tag=selected_tag,
                           all_tags=sorted(all_tags),
                           insights=insights,
                           alerts=alerts,
                           )


@app.route('/analytics')
@login_required
def analytics():
    user = get_current_user()
    total_spent = db.session.query(func.sum(Expense.amount))\
        .filter_by(user_id=user.id).scalar() or 0

    category_data, monthly_data, mom_change = get_analytics_data(user.id)

    cat_budgets = {cb.category: cb.limit for cb in
                   CategoryBudget.query.filter_by(user_id=user.id).all()}

    return render_template('analytics.html',
                           user=user,
                           total_spent=total_spent,
                           monthly_limit=user.monthly_limit,
                           currency=user.currency,
                           category_data=category_data,
                           monthly_data=monthly_data,
                           mom_change=mom_change,
                           cat_budgets=cat_budgets,
                           )


@app.route('/expenses')
@login_required
def expense_history():
    user = get_current_user()
    search_q = request.args.get('q', '')
    tag_q = request.args.get('tag', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Expense.query.filter_by(user_id=user.id)
    if search_q:
        query = query.filter(
            (Expense.category.ilike(f'%{search_q}%')) |
            (Expense.notes.ilike(f'%{search_q}%')) |
            (Expense.tags.ilike(f'%{search_q}%'))
        )
    if tag_q:
        query = query.filter(Expense.tags.ilike(f'%{tag_q}%'))

    total_count = query.count()
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    expenses = query.order_by(Expense.date.desc())\
        .offset((page - 1) * per_page).limit(per_page).all()

    # All tags for filter
    all_expenses = Expense.query.filter_by(user_id=user.id).all()
    all_tags = set()
    for e in all_expenses:
        if e.tags:
            for t in e.tags.split(','):
                t = t.strip()
                if t:
                    all_tags.add(t)

    return render_template('expenses.html',
                           user=user,
                           expenses=expenses,
                           search_q=search_q,
                           tag_q=tag_q,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count,
                           all_tags=sorted(all_tags),
                           )


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    user = get_current_user()
    exp = Expense.query.filter_by(id=id, user_id=user.id).first_or_404()
    db.session.delete(exp)
    db.session.commit()
    return redirect(url_for('expense_history'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    user = get_current_user()
    exp = Expense.query.filter_by(id=id, user_id=user.id).first_or_404()

    if request.method == 'POST':
        exp.amount = float(request.form.get('amount'))
        exp.category = request.form.get('category')
        exp.notes = request.form.get('notes', '')
        exp.tags = request.form.get('tags', '')
        exp.is_recurring = request.form.get('is_recurring') == 'on'
        exp.recurrence = request.form.get(
            'recurrence', '') if exp.is_recurring else ''
        db.session.commit()
        return redirect(url_for('expense_history'))

    return render_template('edit.html', user=user, expense=exp)


# ═══════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user = get_current_user()
    error = None
    success = None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'profile':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            if not name or not email:
                error = 'Name and email are required.'
            elif email != user.email and User.query.filter_by(email=email).first():
                error = 'That email is already in use.'
            else:
                user.name = name
                user.email = email
                db.session.commit()
                success = 'Profile updated successfully.'

        elif action == 'password':
            current = request.form.get('current_password', '')
            new_pwd = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            if not bcrypt.checkpw(current.encode(), user.password.encode()):
                error = 'Current password is incorrect.'
            elif len(new_pwd) < 6:
                error = 'New password must be at least 6 characters.'
            elif new_pwd != confirm:
                error = 'Passwords do not match.'
            else:
                user.password = bcrypt.hashpw(
                    new_pwd.encode(), bcrypt.gensalt()).decode()
                db.session.commit()
                success = 'Password changed successfully.'

        elif action == 'preferences':
            user.currency = request.form.get('currency', '₹')
            user.monthly_limit = float(request.form.get('monthly_limit', 5000))
            user.theme = request.form.get('theme', 'light')
            db.session.commit()
            success = 'Preferences saved.'

        elif action == 'delete_account':
            confirm_text = request.form.get('confirm_delete', '')
            if confirm_text == 'DELETE':
                db.session.delete(user)
                db.session.commit()
                resp = make_response(redirect(url_for('landing')))
                resp.delete_cookie('token')
                return resp
            else:
                error = 'Type DELETE to confirm account deletion.'

    return render_template('settings.html',
                           user=user, error=error, success=success,
                           currencies=CURRENCY_SYMBOLS)


# ═══════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════

def check_budget_alerts(user):
    """Return list of categories that crossed 80% of their budget."""
    alerts = []
    budgets = CategoryBudget.query.filter_by(user_id=user.id).all()
    now = datetime.utcnow()
    for b in budgets:
        spent = db.session.query(func.sum(Expense.amount))\
            .filter_by(user_id=user.id, category=b.category)\
            .filter(
                extract('month', Expense.date) == now.month,
                extract('year',  Expense.date) == now.year,
        ).scalar() or 0
        pct = (spent / b.limit) * 100 if b.limit > 0 else 0
        if pct >= 80:
            alerts.append({
                'category': b.category,
                'pct': round(pct, 1),
                'spent': round(spent, 2),
                'limit': b.limit
            })
    return alerts


@app.route('/api/set-limit', methods=['POST'])
@login_required
def set_limit():
    user = get_current_user()
    data = request.get_json()
    limit = float(data.get('limit', 5000))
    if limit <= 0:
        return jsonify({'error': 'Invalid limit'}), 400
    user.monthly_limit = limit
    db.session.commit()
    return jsonify({'success': True, 'limit': limit})


@app.route('/api/set-category-budget', methods=['POST'])
@login_required
def set_category_budget():
    user = get_current_user()
    data = request.get_json()
    category = data.get('category')
    limit = float(data.get('limit', 0))
    existing = CategoryBudget.query.filter_by(
        user_id=user.id, category=category).first()
    if existing:
        existing.limit = limit
    else:
        db.session.add(CategoryBudget(user_id=user.id,
                       category=category, limit=limit))
    db.session.commit()
    # Check if already over 80%
    alerts = check_budget_alerts(user)
    return jsonify({'success': True, 'alerts': alerts})


@app.route('/api/save-theme', methods=['POST'])
@login_required
def save_theme():
    user = get_current_user()
    data = request.get_json()
    theme = data.get('theme', 'light')
    if theme in ('light', 'dark'):
        user.theme = theme
        db.session.commit()
    return jsonify({'success': True})


@app.route('/export/csv')
@login_required
def export_csv():
    user = get_current_user()
    expenses = Expense.query.filter_by(user_id=user.id)\
        .order_by(Expense.date.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Category', 'Amount',
                    'Notes', 'Tags', 'Recurring'])
    for e in expenses:
        writer.writerow([
            e.date.strftime('%Y-%m-%d'),
            e.category,
            f'{e.amount:.2f}',
            e.notes or '',
            e.tags or '',
            'Yes' if e.is_recurring else 'No',
        ])
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers[
        'Content-Disposition'] = f'attachment; filename=expenses_{user.name.replace(" ", "_")}.csv'
    return response


if __name__ == '__main__':
    app.run(debug=True)
