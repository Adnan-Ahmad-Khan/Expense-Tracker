from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from datetime import datetime

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()


@app.route("/", methods=["GET", "POST"])
def home():
    # ---------- ADD EXPENSE ----------
    if request.method == "POST":
        amount = float(request.form.get("amount"))
        category = request.form.get("category")

        db.session.add(Expense(amount=amount, category=category))
        db.session.commit()
        return redirect(url_for("home"))

    # ---------- FILTERS ----------
    selected_month = request.args.get("month")
    selected_category = request.args.get("category")

    query = Expense.query

    if selected_category:
        query = query.filter(Expense.category == selected_category)

    if selected_month:
        year, month = selected_month.split("-")
        query = query.filter(
            extract("year", Expense.date) == int(year),
            extract("month", Expense.date) == int(month),
        )

    expenses = query.order_by(Expense.date.desc()).all()

    # ---------- TOTALS ----------
    total_spent = sum(e.amount for e in expenses)
    monthly_limit = 5000

    # ---------- CATEGORY DATA ----------
    category_data = (
        db.session.query(Expense.category, func.sum(Expense.amount))
        .group_by(Expense.category)
        .all()
    )
    category_data = [(c, float(t)) for c, t in category_data]

    # ---------- MONTHLY TREND ----------
    monthly_data = (
        db.session.query(
            extract("month", Expense.date),
            extract("year", Expense.date),
            func.sum(Expense.amount),
        )
        .group_by(extract("month", Expense.date), extract("year", Expense.date))
        .order_by(extract("year", Expense.date), extract("month", Expense.date))
        .all()
    )

    monthly_data = [
        (f"{int(m)}/{int(y)}", float(t)) for m, y, t in monthly_data
    ]

    # ---------- FILTER DROPDOWNS ----------
    categories = [c[0]
                  for c in db.session.query(Expense.category).distinct().all()]

    months = [
        f"{y}-{m:02d}"
        for y, m in db.session.query(
            extract("year", Expense.date),
            extract("month", Expense.date),
        )
        .distinct()
        .order_by(extract("year", Expense.date), extract("month", Expense.date))
        .all()
    ]

    return render_template(
        "index.html",
        expenses=expenses,
        total_spent=total_spent,
        monthly_limit=monthly_limit,
        category_data=category_data,
        monthly_data=monthly_data,
        categories=categories,
        months=months,
        selected_month=selected_month,
        selected_category=selected_category,
    )


@app.route("/expenses")
def expense_history():
    expenses = Expense.query.order_by(Expense.date.desc()).all()
    return render_template("expenses.html", expenses=expenses)

# Add this route to your app.py (paste it after the expense_history route)


@app.route("/analytics")
def analytics():
    total_spent = db.session.query(func.sum(Expense.amount)).scalar() or 0
    monthly_limit = 5000

    category_data = (
        db.session.query(Expense.category, func.sum(Expense.amount))
        .group_by(Expense.category)
        .all()
    )
    category_data = [(c, float(t)) for c, t in category_data]

    monthly_data = (
        db.session.query(
            extract("month", Expense.date),
            extract("year", Expense.date),
            func.sum(Expense.amount),
        )
        .group_by(extract("month", Expense.date), extract("year", Expense.date))
        .order_by(extract("year", Expense.date), extract("month", Expense.date))
        .all()
    )
    monthly_data = [(f"{int(m)}/{int(y)}", float(t))
                    for m, y, t in monthly_data]

    return render_template(
        "analytics.html",
        total_spent=total_spent,
        monthly_limit=monthly_limit,
        category_data=category_data,
        monthly_data=monthly_data,
    )


@app.route("/delete/<int:id>")
def delete(id):
    exp = Expense.query.get_or_404(id)
    db.session.delete(exp)
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    exp = Expense.query.get_or_404(id)

    if request.method == "POST":
        exp.amount = float(request.form.get("amount"))
        exp.category = request.form.get("category")
        db.session.commit()
        return redirect(url_for("home"))

    return render_template("edit.html", expense=exp)


if __name__ == "__main__":
    app.run(debug=True)
