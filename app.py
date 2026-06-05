from flask import Flask, render_template, request, redirect, url_for, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import bcrypt
import jwt
import os
import csv
import io

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET'] = os.environ.get(
    'JWT_SECRET', 'your-secret-key-change-in-production')

db = SQLAlchemy(app)


# ─────────────────────────────────────────
#  MODELS
# ─────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    monthly_limit = db.Column(db.Float, default=5000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expenses = db.relationship('Expense', backref='user', lazy=True)
    cat_budgets = db.relationship('CategoryBudget', backref='user', lazy=True)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.String(255), default='')
    is_recurring = db.Column(db.Boolean, default=False)
    # 'weekly' | 'monthly' | ''
    recurrence = db.Column(db.String(20), default='')
    date = db.Column(db.DateTime, default=datetime.utcnow)


class CategoryBudget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    limit = db.Column(db.Float, nullable=False)


with app.app_context():
    db.create_all()


# ─────────────────────────────────────────
#  JWT HELPERS
# ─────────────────────────────────────────

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
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def login_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────

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
    resp = make_response(redirect(url_for('login')))
    resp.delete_cookie('token')
    return resp


# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────

def get_analytics_data(user_id):
    """Shared analytics logic for home + analytics pages."""
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

    # Month-over-month change
    mom_change = None
    if len(monthly_data) >= 2:
        prev = monthly_data[-2][1]
        curr = monthly_data[-1][1]
        if prev > 0:
            mom_change = round(((curr - prev) / prev) * 100, 1)

    return category_data, monthly_data, mom_change


# ─────────────────────────────────────────
#  MAIN ROUTES
# ─────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
@login_required
def home():
    user = get_current_user()

    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        category = request.form.get('category')
        notes = request.form.get('notes', '')
        is_recurring = request.form.get('is_recurring') == 'on'
        recurrence = request.form.get('recurrence', '') if is_recurring else ''

        db.session.add(Expense(
            user_id=user.id, amount=amount, category=category,
            notes=notes, is_recurring=is_recurring, recurrence=recurrence
        ))
        db.session.commit()
        return redirect(url_for('home', added=1))

    # Filters
    selected_month = request.args.get('month')
    selected_category = request.args.get('category')
    search_query = request.args.get('q', '')

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
            (Expense.notes.ilike(f'%{search_query}%'))
        )

    expenses = query.order_by(Expense.date.desc()).all()
    total_spent = sum(
        e.amount for e in Expense.query.filter_by(user_id=user.id).all())

    category_data, monthly_data, _ = get_analytics_data(user.id)

    categories = [c[0] for c in db.session.query(Expense.category)
                  .filter_by(user_id=user.id).distinct().all()]
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

    return render_template('index.html',
                           user=user,
                           expenses=expenses,
                           total_spent=total_spent,
                           monthly_limit=user.monthly_limit,
                           category_data=category_data,
                           monthly_data=monthly_data,
                           categories=categories,
                           months=months,
                           selected_month=selected_month,
                           selected_category=selected_category,
                           search_query=search_query,
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
    query = Expense.query.filter_by(user_id=user.id)
    if search_q:
        query = query.filter(
            (Expense.category.ilike(f'%{search_q}%')) |
            (Expense.notes.ilike(f'%{search_q}%'))
        )
    expenses = query.order_by(Expense.date.desc()).all()
    return render_template('expenses.html', user=user,
                           expenses=expenses, search_q=search_q)


@app.route('/delete/<int:id>')
@login_required
def delete(id):
    user = get_current_user()
    exp = Expense.query.filter_by(id=id, user_id=user.id).first_or_404()
    db.session.delete(exp)
    db.session.commit()
    return redirect(url_for('home'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    user = get_current_user()
    exp = Expense.query.filter_by(id=id, user_id=user.id).first_or_404()

    if request.method == 'POST':
        exp.amount = float(request.form.get('amount'))
        exp.category = request.form.get('category')
        exp.notes = request.form.get('notes', '')
        exp.is_recurring = request.form.get('is_recurring') == 'on'
        exp.recurrence = request.form.get(
            'recurrence', '') if exp.is_recurring else ''
        db.session.commit()
        return redirect(url_for('home'))

    return render_template('edit.html', user=user, expense=exp)


# ─────────────────────────────────────────
#  API ROUTES
# ─────────────────────────────────────────

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
        db.session.add(CategoryBudget(
            user_id=user.id, category=category, limit=limit))
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
    writer.writerow(['Date', 'Category', 'Amount', 'Notes', 'Recurring'])
    for e in expenses:
        writer.writerow([
            e.date.strftime('%Y-%m-%d'),
            e.category,
            f'{e.amount:.2f}',
            e.notes or '',
            'Yes' if e.is_recurring else 'No',
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = 'attachment; filename=expenses.csv'
    return response


if __name__ == '__main__':
    app.run(debug=True)
