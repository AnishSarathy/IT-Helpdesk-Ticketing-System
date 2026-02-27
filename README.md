# HelpDesk Pro — IT Service Desk Ticketing System

A web-based IT ticketing system I built to understand how real helpdesk tools like ServiceNow actually work under the hood. The entire platform runs on Flask and SQLite with no frontend frameworks, just plain HTML, CSS, and a bit of JavaScript. 

---

## What it does

There are three roles — Admin, Technician, and User — and each one sees a different version of the app.

Users can submit tickets, track their status, and remove them from their view once they're resolved or closed. Technicians get assigned tickets automatically based on who has the lightest workload at that moment, and they can update status as they work through them. Admins see everything, can reassign tickets, and have access to a global audit log.

A few things I thought were worth building properly:

- **Auto-assignment** — when a ticket comes in, it checks which tech has the fewest active tickets and routes it there. Ties are broken randomly.
- **Ticket lifecycle** — tickets go Open → In Progress → Resolved, then automatically move to Closed after 24 hours. After 7 days in Closed they're permanently deleted. Nobody can manually close a ticket.
- **Role-scoped views** — techs only see their own queue, not other techs' tickets. Analytics shows personal stats for techs and company-wide stats for admins.
- **Audit log** — every status change and reassignment is logged, scoped to what's relevant for each role. Shows the last 30 days.

---

## Tech stack

| | |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite |
| Frontend | HTML, CSS, JS |
| Auth | Flask sessions |

---

## Running it locally

You'll need Python 3.6+ and pip.

```bash
git clone https://github.com/AnishSarathy/IT-Helpdesk-Ticketing-System.git
cd IT-Helpdesk-Ticketing-System
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000` in your browser. The database gets created automatically on first run.

---

## Demo accounts

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin |
| tech1 | tech123 | Technician |
| tech2 | tech123 | Technician |
| anish | user123 | User |

---

## Project structure

```
it-helpdesk/
├── app.py                 # All routes, DB logic, and auth
├── requirements.txt
├── tickets.db             # Auto-created on first run
└── templates/
    ├── base.html          # Nav and shared styles
    ├── login.html
    ├── register.html
    ├── dashboard.html     # Tabbed ticket list
    ├── submit.html
    ├── ticket_detail.html
    ├── analytics.html
    ├── audit.html
    └── settings.html
```

---

## Future improvements

- Password hashing — right now passwords are stored in plain text which is obviously not production-ready
- Email notifications when a ticket gets assigned or resolved
- File attachments on tickets
- SLA tracking with breach alerts
- A proper REST API

---

## License

MIT
