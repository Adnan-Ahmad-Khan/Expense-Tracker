# Expense Tracker

A full-stack personal finance dashboard built with **Flask**, **SQLAlchemy**, and **Chart.js**. Features JWT authentication, multi-user support, spending analytics, category budgets, recurring expenses, tags, CSV export, and a fully responsive dark/light UI.

---

## Screenshot

> <img width="700" height="580" alt="image" src="https://github.com/user-attachments/assets/3fef6baa-ddd6-4281-a5cc-289f4ed64c77" />


---

##  Features

### 🔐 Authentication
* **Secure JWT Auth:** Tokens stored in secure `httpOnly` cookies with a 7-day expiration.
* **Encryption:** Passwords safely hashed using `bcrypt`.
* **Data Isolation:** Complete per-user data protection ensuring users only access their own data.

### 📊 Dashboard & Analytics
* **Visual Insights:** Animated Chart.js donut and bar charts showing spending patterns and budget thresholds.
* **Smart Budgets:** Color-coded progress metrics (Green ➔ Amber ➔ Red) with live toast alerts when crossing 80% of a category limit.
* **Auto-Insights:** Real-time generation of trends, top spending days, and month-over-month percentage changes.
* **UX Optimizations:** Inline budget editor, live search with 450ms debounce, and global keyboard shortcuts (`N` to add expense, `/` to search).

### 📋 Expense History & Settings
* **Management:** Full paginated table (20/page), tag filtering, and multi-field CSV export.
* **Flexibility:** Track recurring expenses (weekly/monthly) and customize categories.
* **Preferences:** Device-synced light/dark mode, profile updates with live avatars, and currency configuration (₹, $, €, £).
---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask |
| Database | SQLite via Flask-SQLAlchemy |
| Auth | PyJWT + bcrypt |
| Charts | Chart.js |
| Frontend | Vanilla JS, CSS custom properties |
| Fonts | Google Fonts (Plus Jakarta Sans, Manrope) |

---

## Project Structure

```
expense-tracker/
│
├── app.py                  # Flask app — routes, models, JWT auth
│
├── templates/
│   ├── landing.html        # Public landing page
│   ├── login.html          # Sign in
│   ├── register.html       # Create account
│   ├── index.html          # Dashboard (protected)
│   ├── analytics.html      # Analytics (protected)
│   ├── expenses.html       # Expense history (protected)
│   ├── edit.html           # Edit expense (protected)
│   └── settings.html       # User settings (protected)
│
├── static/
│   └── css/
│       └── style.css       # Full stylesheet with CSS variables + animations
│
├── expense.db              # SQLite database (auto-created)
└── requirements.txt
```

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/your-username/expense-tracker.git
cd expense-tracker
```

### 2. Create a virtual environment

```bash
python -m venv env

# Windows
env\Scripts\activate

# macOS / Linux
source env/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
python app.py
```

Visit **http://127.0.0.1:5000** — you'll be redirected to the landing page. Register an account to get started.

---

## Requirements

Create a `requirements.txt` with:

```
flask
flask-sqlalchemy
PyJWT
bcrypt
```

Or generate it from your environment:

```bash
pip freeze > requirements.txt
```

---

## Environment Variables

The app works out of the box with defaults. For production, set these:

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `your-secret-key-change-in-production` | Secret used to sign JWT tokens |
| `SECRET_KEY` | `flask-secret-change-in-production` | Flask session secret |

```bash
# Example
export JWT_SECRET=your-very-long-random-secret
export SECRET_KEY=another-random-secret
```

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Landing page (redirects to dashboard if logged in) |
| `GET/POST` | `/register` | Create account |
| `GET/POST` | `/login` | Sign in |
| `GET` | `/logout` | Sign out, clear cookie |
| `GET` | `/switch-account` | Clear session → login |
| `GET/POST` | `/dashboard` | Main dashboard |
| `GET` | `/analytics` | Analytics page |
| `GET` | `/expenses` | Paginated expense history |
| `GET/POST` | `/edit/<id>` | Edit an expense |
| `GET` | `/delete/<id>` | Delete an expense |
| `GET/POST` | `/settings` | User settings |
| `GET` | `/export/csv` | Download all expenses as CSV |
| `POST` | `/api/set-limit` | Update monthly budget limit |
| `POST` | `/api/set-category-budget` | Set per-category budget |
| `POST` | `/api/save-theme` | Save dark/light preference to DB |

---

## Database Models

### `User`
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `name` | String | Display name |
| `email` | String | Unique email |
| `password` | String | bcrypt hash |
| `monthly_limit` | Float | Budget limit (default 5000) |
| `currency` | String | Currency symbol (₹ $ € £) |
| `theme` | String | `light` or `dark` |
| `created_at` | DateTime | Registration date |

### `Expense`
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `user_id` | FK → User | Owner |
| `amount` | Float | Expense amount |
| `category` | String | Category name |
| `notes` | String | Optional note |
| `tags` | String | Comma-separated tags |
| `is_recurring` | Boolean | Recurring flag |
| `recurrence` | String | `weekly` or `monthly` |
| `date` | DateTime | When added |

### `CategoryBudget`
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `user_id` | FK → User | Owner |
| `category` | String | Category name |
| `limit` | Float | Budget limit |

---

## Resetting the Database

If you update the models and get `OperationalError: no such column`, delete the database file and restart:

```bash
# Delete the DB
del expense.db        # Windows
rm expense.db         # macOS / Linux

# Restart Flask — SQLAlchemy recreates it fresh
python app.py
```

For production schema migrations without data loss, use **Flask-Migrate**:

```bash
pip install flask-migrate
```

---
