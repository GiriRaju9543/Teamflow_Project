# Teamflow_Project

A Django web application for managing software-team tasks and automating
task updates from GitHub pull-request events.

## Features

- User registration, login and team memberships.
- Multiple projects with task assignments and reviewers.
- Five task statuses: Not started, In progress, Waiting for review,
  Completed and Changes requested.
- GitHub webhook integration for pull requests and reviews.
- Background processing and in-app review reminders.
- Task history, notifications, reports and CSV export.
- SQLite backup and restoration verification.

## Technology Stack

- Python and Django
- HTML, CSS and Django templates
- SQLite and Django ORM
- GitHub webhooks
- Cloudflare Tunnel for local webhook demonstrations

## Run Locally on Windows

Prerequisites: Python 3.12 and Git.

### 1. Download the project

```powershell
git clone https://github.com/GiriRaju9543/Teamflow_Project.git
cd Teamflow_Project
```

For a private repository, authenticate with an account that has access.

### 2. Create a virtual environment

```powershell
py -3.12 -m venv .venv
```

### 3. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Initialize the database

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

### 5. Start the website

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/ in your browser.

Create an account through the registration page, then create your project.
Teammates must register before a team leader can add them to a workspace.

## Run GitHub Automation

Run each command in a separate terminal from the project folder.

### Background worker

```powershell
.\.venv\Scripts\python.exe manage.py runworker
```

### Webhook receiver

```powershell
.\.venv\Scripts\python.exe manage.py runwebhook
```

### Temporary public tunnel

Install cloudflared separately, then run:

```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```

In Teamflow, configure the project's GitHub repository as `owner/repository`.

In GitHub repository settings, create a webhook using:

- Payload URL: current tunnel address + the project's webhook path.
- Content type: `application/json`.
- Secret: the corresponding project secret shown privately in Teamflow.
- Events: Pull requests and Pull request reviews.
- SSL verification: enabled.

Update the webhook Payload URL whenever the temporary tunnel address changes.

## How Task Automation Works

1. A leader creates a task and assigns a developer and reviewer.
2. The assignee or leader clicks Start task.
3. The developer creates a GitHub pull request containing exactly one
   distinct task reference, such as `TASK-8`, in its title or description.
4. GitHub sends a signed webhook.
5. Teamflow validates and stores the delivery.
6. The worker processes it and updates the linked task.
7. A non-draft pull request can move the task to Waiting for review.
8. A merge event moves the task to Completed.

A recognized approval alone does not complete a task; a human merge is
still required. GitHub review events require the assigned reviewer's
GitHub username mapping in Teamflow.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py test
```

## Backup Verification

```powershell
.\.venv\Scripts\python.exe manage.py verify_sqlite_backup
```

This creates a backup and verifies a separate restored copy.
It does not replace the live database.

## Local Data and Configuration

SQLite data is stored in `.local/teamflow.sqlite3`.

The repository excludes local databases, secrets and virtual environments.
A fresh clone does not contain the original installation's users or tasks.

`.env.example` documents available environment settings.
The application does not automatically load that file.

## Current Scope

This project is configured for local development and demonstrations.
Permanent production hosting and real email delivery are not included.

## Additional Instructions

See [Run Teamflow Yourself](RUN-TEAMFLOW-YOURSELF.md).