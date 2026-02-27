from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "it-helpdesk-secret-2024"
DB = "tickets.db"

# DATABASE SETUP

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','technician','user'))
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL CHECK(priority IN ('Low','Medium','High','Critical')),
                status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','In Progress','Resolved','Closed')),
                submitted_by INTEGER,
                assigned_to INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                hidden_by_user INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(submitted_by) REFERENCES users(id),
                FOREIGN KEY(assigned_to) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                actor_id INTEGER,
                actor_name TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(id),
                FOREIGN KEY(actor_id) REFERENCES users(id)
            );

            INSERT OR IGNORE INTO users (username, password, role) VALUES
                ('admin',  'admin123',  'admin'),
                ('tech1',  'tech123',   'technician'),
                ('tech2',  'tech123',   'technician'),
                ('anish',  'user123',   'user');
        """)
        # Migrate existing tickets table if columns missing
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN hidden_by_user INTEGER NOT NULL DEFAULT 0")
        except:
            pass
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN resolved_at TEXT")
        except:
            pass
        try:
            conn.execute("ALTER TABLE tickets ADD COLUMN closed_at TEXT")
        except:
            pass

def auto_assign(db):
    """Return the technician id with the lowest active (Open/In Progress) ticket count."""
    import random
    techs = db.execute("SELECT id FROM users WHERE role='technician'").fetchall()
    if not techs:
        return None
    workloads = []
    for tech in techs:
        count = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE assigned_to=? AND status IN ('Open','In Progress')",
            (tech["id"],)
        ).fetchone()[0]
        workloads.append((tech["id"], count))
    min_load = min(w[1] for w in workloads)
    least_loaded = [w[0] for w in workloads if w[1] == min_load]
    return random.choice(least_loaded)

def log_audit(db, ticket_id, action, detail=None):
    db.execute(
        "INSERT INTO audit_log (ticket_id, actor_id, actor_name, action, detail, created_at) VALUES (?,?,?,?,?,?)",
        (ticket_id, session.get("user_id"), session.get("username"), action, detail, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

def run_auto_transitions(db):
    """Auto-close resolved tickets after 24h; auto-delete closed tickets after 7 days."""
    now = datetime.now()

    # 1. Resolved to Closed after 24 hours
    resolved = db.execute(
        "SELECT id, resolved_at FROM tickets WHERE status='Resolved' AND resolved_at IS NOT NULL"
    ).fetchall()
    for t in resolved:
        age = now - datetime.strptime(t["resolved_at"], "%Y-%m-%d %H:%M:%S")
        if age.total_seconds() >= 86400:  # 24 hours
            closed_at = now.strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "UPDATE tickets SET status='Closed', closed_at=?, updated_at=? WHERE id=?",
                (closed_at, closed_at, t["id"])
            )
            db.execute(
                "INSERT INTO audit_log (ticket_id, actor_id, actor_name, action, detail, created_at) VALUES (?,?,?,?,?,?)",
                (t["id"], None, "System", "Auto-Closed", "Automatically closed 24h after resolution", closed_at)
            )

    # 2. Delete Closed tickets after 7 days
    closed = db.execute(
        "SELECT id, closed_at FROM tickets WHERE status='Closed' AND closed_at IS NOT NULL"
    ).fetchall()
    for t in closed:
        age = now - datetime.strptime(t["closed_at"], "%Y-%m-%d %H:%M:%S")
        if age.total_seconds() >= 604800:  # 7 days
            db.execute("DELETE FROM audit_log WHERE ticket_id=?", (t["id"],))
            db.execute("DELETE FROM tickets WHERE id=?", (t["id"],))


    import random
    techs = db.execute("SELECT id FROM users WHERE role='technician'").fetchall()
    if not techs:
        return None
    workloads = []
    for tech in techs:
        count = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE assigned_to=? AND status IN ('Open','In Progress')",
            (tech["id"],)
        ).fetchone()[0]
        workloads.append((tech["id"], count))
    min_load = min(w[1] for w in workloads)
    return __import__('random').choice([w[0] for w in workloads if w[1] == min_load])

# AUTH HELPERS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_or_tech(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") not in ("admin", "technician"):
            flash("Access denied.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

# ROUTES 

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u, p = request.form["username"], request.form["password"]
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p)).fetchone()
        if user:
            session.update(user_id=user["id"], username=user["username"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    with get_db() as db:
        all_users = db.execute("SELECT username, password, role FROM users ORDER BY role, username").fetchall()
    return render_template("login.html", all_users=all_users)

@app.route("/register", methods=["GET","POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        confirm  = request.form["confirm"].strip()
        if not username or not password:
            flash("Username and password are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                               (username, password, "user"))
                flash("Account created! You can now log in.", "success")
                return redirect(url_for("login"))
            except:
                flash("Username already taken.", "danger")
    return render_template("register.html")

@app.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    uid = session["user_id"]
    with get_db() as db:
        db.execute("UPDATE tickets SET assigned_to=NULL WHERE assigned_to=?", (uid,))
        db.execute("UPDATE tickets SET submitted_by=NULL WHERE submitted_by=?", (uid,))
        db.execute("DELETE FROM users WHERE id=?", (uid,))
    session.clear()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    tab            = request.args.get("tab", "active")   # active | resolved | closed
    priority_filter = request.args.get("priority", "")

    # Map tab to status filter(s)
    if tab == "resolved":
        status_clause = "t.status = 'Resolved'"
    elif tab == "closed":
        status_clause = "t.status = 'Closed'"
    else:
        status_clause = "t.status IN ('Open','In Progress')"

    query = f"""
        SELECT t.*, u1.username AS submitter, u2.username AS assignee
        FROM tickets t
        LEFT JOIN users u1 ON t.submitted_by = u1.id
        LEFT JOIN users u2 ON t.assigned_to  = u2.id
        WHERE {status_clause}
    """
    params = []
    if priority_filter:
        query += " AND t.priority = ?"; params.append(priority_filter)

    if session["role"] == "technician":
        query += " AND (t.assigned_to IS NULL OR t.assigned_to = ?)"; params.append(session["user_id"])
    elif session["role"] == "user":
        query += " AND t.submitted_by = ? AND t.hidden_by_user = 0"; params.append(session["user_id"])

    query += " ORDER BY t.created_at DESC"

    with get_db() as db:
        run_auto_transitions(db)
        tickets = db.execute(query, params).fetchall()
        uid = session["user_id"]
        if session["role"] == "user":
            stats = {
                "open":        db.execute("SELECT COUNT(*) FROM tickets WHERE status='Open' AND submitted_by=? AND hidden_by_user=0", (uid,)).fetchone()[0],
                "in_progress": db.execute("SELECT COUNT(*) FROM tickets WHERE status='In Progress' AND submitted_by=? AND hidden_by_user=0", (uid,)).fetchone()[0],
                "resolved":    db.execute("SELECT COUNT(*) FROM tickets WHERE status='Resolved' AND submitted_by=? AND hidden_by_user=0", (uid,)).fetchone()[0],
                "critical":    db.execute("SELECT COUNT(*) FROM tickets WHERE priority='Critical' AND status NOT IN ('Resolved','Closed') AND submitted_by=? AND hidden_by_user=0", (uid,)).fetchone()[0],
            }
        elif session["role"] == "technician":
            stats = {
                "open":        db.execute("SELECT COUNT(*) FROM tickets WHERE status='Open' AND (assigned_to=? OR assigned_to IS NULL)", (uid,)).fetchone()[0],
                "in_progress": db.execute("SELECT COUNT(*) FROM tickets WHERE status='In Progress' AND assigned_to=?", (uid,)).fetchone()[0],
                "resolved":    db.execute("SELECT COUNT(*) FROM tickets WHERE status='Resolved' AND assigned_to=?", (uid,)).fetchone()[0],
                "critical":    db.execute("SELECT COUNT(*) FROM tickets WHERE priority='Critical' AND status NOT IN ('Resolved','Closed') AND (assigned_to=? OR assigned_to IS NULL)", (uid,)).fetchone()[0],
            }
        else:
            stats = {
                "open":        db.execute("SELECT COUNT(*) FROM tickets WHERE status='Open'").fetchone()[0],
                "in_progress": db.execute("SELECT COUNT(*) FROM tickets WHERE status='In Progress'").fetchone()[0],
                "resolved":    db.execute("SELECT COUNT(*) FROM tickets WHERE status='Resolved'").fetchone()[0],
                "critical":    db.execute("SELECT COUNT(*) FROM tickets WHERE priority='Critical' AND status NOT IN ('Resolved','Closed')").fetchone()[0],
            }
        techs = db.execute("SELECT * FROM users WHERE role='technician'").fetchall()

    return render_template("dashboard.html", tickets=tickets, stats=stats, techs=techs,
                           tab=tab, priority_filter=priority_filter)

@app.route("/submit", methods=["GET","POST"])
@login_required
def submit_ticket():
    if session.get("role") == "technician":
        flash("Technicians cannot submit tickets.", "danger")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as db:
            assigned_to = auto_assign(db)
            cur = db.execute("""
                INSERT INTO tickets (title, description, category, priority, status, submitted_by, assigned_to, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                request.form["title"], request.form["description"],
                request.form["category"], request.form["priority"],
                "Open", session["user_id"], assigned_to, now, now
            ))
            tech_name = db.execute("SELECT username FROM users WHERE id=?", (assigned_to,)).fetchone()
            log_audit(db, cur.lastrowid, "Ticket Submitted",
                      f"Priority: {request.form['priority']} | Category: {request.form['category']} | Auto-assigned to: {tech_name['username'] if tech_name else 'None'}")
        flash("Ticket submitted and automatically assigned!", "success")
        return redirect(url_for("dashboard"))
    return render_template("submit.html")

@app.route("/ticket/<int:tid>")
@login_required
def ticket_detail(tid):
    with get_db() as db:
        ticket = db.execute("""
            SELECT t.*, u1.username AS submitter, u2.username AS assignee
            FROM tickets t
            LEFT JOIN users u1 ON t.submitted_by = u1.id
            LEFT JOIN users u2 ON t.assigned_to  = u2.id
            WHERE t.id = ?
        """, (tid,)).fetchone()
        techs = db.execute("SELECT * FROM users WHERE role='technician'").fetchall()
    if not ticket:
        flash("Ticket not found.", "danger")
        return redirect(url_for("dashboard"))
    return render_template("ticket_detail.html", ticket=ticket, techs=techs)

@app.route("/ticket/<int:tid>/update", methods=["POST"])
@login_required
@admin_or_tech
def update_ticket(tid):
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = request.form.get("status")
    with get_db() as db:
        ticket = db.execute("SELECT assigned_to, status FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for("dashboard"))
        if session["role"] == "technician" and ticket["assigned_to"] != session["user_id"]:
            flash("You can only update tickets assigned to you.", "danger")
            return redirect(url_for("dashboard"))
        # Block manual Closed since it's set automatically after 24h
        if status == "Closed":
            flash("Tickets are closed automatically 24 hours after being resolved.", "danger")
            return redirect(url_for("ticket_detail", tid=tid))
        old_status = ticket["status"]
        resolved_at_update = ""
        if status == "Resolved" and old_status != "Resolved":
            resolved_at_update = f", resolved_at='{now}'"
        if session["role"] == "admin":
            assigned_to = request.form.get("assigned_to") or ticket["assigned_to"]
            db.execute(f"UPDATE tickets SET status=?, assigned_to=?, updated_at=?{resolved_at_update} WHERE id=?",
                       (status, assigned_to, now, tid))
            detail_parts = []
            if old_status != status:
                detail_parts.append(f"Status: {old_status} → {status}")
            if str(assigned_to) != str(ticket["assigned_to"]):
                new_tech = db.execute("SELECT username FROM users WHERE id=?", (assigned_to,)).fetchone()
                detail_parts.append(f"Reassigned to: {new_tech['username'] if new_tech else 'None'}")
            log_audit(db, tid, "Ticket Updated", " | ".join(detail_parts) if detail_parts else "No changes")
        else:
            db.execute(f"UPDATE tickets SET status=?, updated_at=?{resolved_at_update} WHERE id=?",
                       (status, now, tid))
            if old_status != status:
                log_audit(db, tid, "Status Changed", f"{old_status} → {status}")
    flash("Ticket updated.", "success")
    return redirect(url_for("ticket_detail", tid=tid))

@app.route("/ticket/<int:tid>/hide", methods=["POST"])
@login_required
def hide_ticket(tid):
    """User soft-deletes a resolved/closed ticket — hidden from their view only."""
    with get_db() as db:
        ticket = db.execute("SELECT submitted_by, status FROM tickets WHERE id=?", (tid,)).fetchone()
        if not ticket:
            flash("Ticket not found.", "danger")
        elif ticket["submitted_by"] != session["user_id"]:
            flash("You can only remove your own tickets.", "danger")
        elif ticket["status"] not in ("Resolved", "Closed"):
            flash("You can only remove resolved or closed tickets.", "danger")
        else:
            db.execute("UPDATE tickets SET hidden_by_user=1 WHERE id=?", (tid,))
            flash("Ticket removed from your view.", "success")
    return redirect(url_for("dashboard"))

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@app.route("/analytics")
@login_required
@admin_or_tech
def analytics():
    with get_db() as db:
        if session["role"] == "technician":
            uid = session["user_id"]
            by_status   = db.execute("SELECT status,   COUNT(*) c FROM tickets WHERE assigned_to=? GROUP BY status",   (uid,)).fetchall()
            by_priority = db.execute("SELECT priority, COUNT(*) c FROM tickets WHERE assigned_to=? GROUP BY priority", (uid,)).fetchall()
            by_category = db.execute("SELECT category, COUNT(*) c FROM tickets WHERE assigned_to=? GROUP BY category", (uid,)).fetchall()
            recent      = db.execute("""
                SELECT t.*, u.username AS submitter FROM tickets t
                LEFT JOIN users u ON t.submitted_by = u.id
                WHERE t.assigned_to = ?
                ORDER BY t.created_at DESC LIMIT 5
            """, (uid,)).fetchall()
            total = db.execute("SELECT COUNT(*) FROM tickets WHERE assigned_to=?", (uid,)).fetchone()[0]
        else:
            by_status   = db.execute("SELECT status,   COUNT(*) c FROM tickets GROUP BY status").fetchall()
            by_priority = db.execute("SELECT priority, COUNT(*) c FROM tickets GROUP BY priority").fetchall()
            by_category = db.execute("SELECT category, COUNT(*) c FROM tickets GROUP BY category").fetchall()
            recent      = db.execute("""
                SELECT t.*, u.username AS submitter FROM tickets t
                LEFT JOIN users u ON t.submitted_by = u.id
                ORDER BY t.created_at DESC LIMIT 5
            """).fetchall()
            total = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    return render_template("analytics.html",
                           by_status=by_status, by_priority=by_priority,
                           by_category=by_category, recent=recent, total=total)

@app.route("/audit")
@login_required
def audit():
    with get_db() as db:
        if session["role"] == "admin":
            logs = db.execute("""
                SELECT a.*, t.title as ticket_title FROM audit_log a
                LEFT JOIN tickets t ON a.ticket_id = t.id
                WHERE a.created_at >= datetime('now', '-30 days')
                ORDER BY a.created_at DESC LIMIT 100
            """).fetchall()
            page_title = "Global Audit Log"
            page_sub   = "All system activity — last 30 days"
        elif session["role"] == "technician":
            uid = session["user_id"]
            logs = db.execute("""
                SELECT a.*, t.title as ticket_title FROM audit_log a
                LEFT JOIN tickets t ON a.ticket_id = t.id
                WHERE t.assigned_to = ?
                AND a.created_at >= datetime('now', '-30 days')
                ORDER BY a.created_at DESC LIMIT 100
            """, (uid,)).fetchall()
            page_title = "My Audit Log"
            page_sub   = "Activity on your assigned tickets — last 30 days"
        else:
            uid = session["user_id"]
            logs = db.execute("""
                SELECT a.*, t.title as ticket_title FROM audit_log a
                LEFT JOIN tickets t ON a.ticket_id = t.id
                WHERE t.submitted_by = ?
                AND a.created_at >= datetime('now', '-30 days')
                ORDER BY a.created_at DESC LIMIT 100
            """, (uid,)).fetchall()
            page_title = "My Ticket History"
            page_sub   = "Status changes on your tickets — last 30 days"
    return render_template("audit.html", logs=logs, page_title=page_title, page_sub=page_sub)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
