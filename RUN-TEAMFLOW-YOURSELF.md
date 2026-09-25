# Teamflow: move, start and use independently

This guide is saved inside the project so it travels with your files. SQLite is the selected database. PostgreSQL, ChatGPT and pgAdmin are not required to run this local app. Python packages and Cloudflare/GitHub access remain separate dependencies. GitHub automation needs internet.

## 1. Move safely

1. In each of the four old terminals, press Ctrl+C: website, worker, webhook receiver and Cloudflare. Stop all four before copying the database.
2. COPY the entire teamflow folder to your chosen destination first. Keep the original until the new copy works.
3. Example destination used below: E:\Teamflow. Replace it with your actual destination in every command.
4. The folder you open must contain manage.py, requirements.txt, config, flow, templates, static and .local.
5. Keep the WHOLE .local folder, especially teamflow.sqlite3 and development-secret. It also holds backups and private credentials/settings if present. Do not publish it on GitHub.
6. Do not run the old and new copies at the same time. They would use separate databases and might compete for ports.

## 2. Open the new location and rebuild Python environment (once per move)

In VS Code: File > Open Folder > select the new Teamflow folder. Terminal > New Terminal.

```powershell
cd "E:\Teamflow"
py -3.12 --version
```

If the command is unavailable on this same laptop, check the installed interpreter:

```powershell
& "C:\Program Files\Python312\python.exe" --version
```

A virtual environment should be recreated after moving. If you copied .venv, rename that folder to .venv-old in File Explorer before continuing. Do not rename or remove .local.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
```

If using the full Python path instead of py, replace only the first command with:

```powershell
& "C:\Program Files\Python312\python.exe" -m venv .venv
```

Package installation requires internet and the exact versions in requirements.txt. If a version is unavailable, stop and resolve that error; do not silently replace versions. The installation has not been rehearsed at your future destination yet.

No Activate.ps1 command is required. Commands below directly use the correct Python. migrate applies database structure updates; it does not recreate demo data. Do not run seed_demo on your existing database.

If you configured POSTGRES_DB in your environment, remove that configuration before using SQLite. For the current terminal only:

```powershell
Remove-Item Env:POSTGRES_DB -ErrorAction SilentlyContinue
```

Normally this is unnecessary: the project currently uses SQLite.

## 3. Start the application every day

Open FOUR VS Code terminals. In each terminal, first run cd with the new folder path. Keep all four running.

### Terminal 1: website

```powershell
cd "E:\Teamflow"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/ in your browser. Use your existing Teamflow login. The copied database retains accounts/passwords. If you forgot a password, run the following in an extra terminal and follow the private prompts:

```powershell
.\.venv\Scripts\python.exe manage.py changepassword giri.demo
```

This changes the password for that existing local user. Do not paste passwords into chat or commit them to GitHub.

### Terminal 2: background worker

```powershell
cd "E:\Teamflow"
.\.venv\Scripts\python.exe manage.py runworker
```

Processes stored GitHub events and creates in-app reminders. Worker active means a heartbeat was recorded within 90 seconds, not that every event succeeded.

### Terminal 3: webhook receiver

```powershell
cd "E:\Teamflow"
.\.venv\Scripts\python.exe manage.py runwebhook
```

Receives signed GitHub events on port 8001. A browser visit to this port is not a valid webhook test; the receiver accepts only the intended POST endpoint.

### Terminal 4: public webhook tunnel

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8001
```

Keep the new https://...trycloudflare.com hostname it prints. A restarted quick tunnel normally has a different hostname. Expose port 8001, not the whole development website on port 8000.

For simply browsing local tasks, only Terminal 1 is necessary. To demonstrate complete live automation, run all four. These commands use your existing installed cloudflared; moving Teamflow does not move or uninstall it.

## 4. Update BOTH GitHub webhooks after starting a new tunnel

Teamflow project URLs remain the same when the complete database is copied.

1. Open http://127.0.0.1:8000/integrations/.
2. Find each project and its Webhook path.
3. Combine the NEW tunnel hostname with that project's path. Do not put the secret in the URL.
4. Open the existing webhook in the relevant GitHub repository's Settings > Webhooks.
5. Replace Payload URL; preserve the existing secret and other correct settings. Save with Update webhook. Do not create another webhook every day.

Shopping Website repository settings:
https://github.com/GiriRaju9543/Project_1/settings/hooks

Its path:
/hooks/github/80515b27-8fb0-4aec-bfbf-eac31ff118be/

House Automation repository settings:
https://github.com/GiriRaju9543/House_Automation_Demo/settings/hooks

Its path:
/hooks/github/ea1f4048-c6ce-4851-b677-c9263863c519/

Example FORMAT ONLY (replace YOUR-NEW-HOST):
https://YOUR-NEW-HOST.trycloudflare.com/hooks/github/ea1f4048-c6ce-4851-b677-c9263863c519/

Settings: application/json; SSL verification enabled; Active; Pull requests and Pull request reviews selected. Push events are not used. Each project has its own secret.

Check the next real delivery in GitHub and Teamflow. New accepted deliveries return 202; an already recorded delivery can return 200. A 202 confirms receipt, not completed processing. Inspect Recent deliveries for the result. Do not assume updating webhook settings automatically produces a fresh ping.

## 5. Useful browser links

- Website and project selector: http://127.0.0.1:8000/
- Login: http://127.0.0.1:8000/login/
- Teams and people: http://127.0.0.1:8000/teams/
- GitHub project connections: http://127.0.0.1:8000/integrations/
- Received events: http://127.0.0.1:8000/deliveries/
- Notifications: http://127.0.0.1:8000/notifications/
- Reports: http://127.0.0.1:8000/reports/
- Shopping repository: https://github.com/GiriRaju9543/Project_1
- House repository: https://github.com/GiriRaju9543/House_Automation_Demo

The localhost links work on the laptop running Teamflow. They are not public website links. Changing a folder does not change these addresses or GitHub repository addresses.

## 6. Complete a new task yourself

1. Select the correct project on the board and click Create task.
2. Enter title, description, assignee, DIFFERENT reviewer and due date; save.
3. Note the actual TASK number. Do not assume TASK-1 or reset numbering again.
4. Click Start task using the assignee or team leader account. State becomes In progress.
5. Open the correct project's GitHub repository. Select main, then create a fresh branch such as task-9-feature (example only; use your actual task).
6. Add/edit the code, test it, and commit to that branch. Commit message and branch name do not have to contain the TASK ID.
7. Pull requests > New pull request: base main, compare your branch.
8. Put exactly one distinct valid task ID in the PR title or description, e.g. TASK-9 Add feature. The remaining title words can differ from the task title. A discussion comment is not the PR description.
9. Create a regular PR. Refresh Teamflow: Waiting for review. Check Recent deliveries if it does not change.
10. Review and test the code before merging. Merge pull request > Confirm merge. Refresh Teamflow: Completed.

One PR links to one task in this version. GitHub PR numbers and Teamflow task numbers are unrelated. Initial matching also checks project membership of the task and repository identity.

## 7. Other workflows

- Corrections: assigned reviewer clicks Request changes in Teamflow with a reason. Task becomes Changes requested. Edit the SAME PR branch and commit the fix. It returns to Waiting for review. Merge after validation.
- This in-app action does not post a GitHub review. Formal GitHub reviews require the appropriate separate account and assigned-reviewer mapping. You cannot approve your own PR.
- Draft: choose Create draft pull request. Task stays In progress. Ready for review moves it to review.
- Close without merge: task returns to In progress. Reopen the same PR to return to review.
- Conflicting IDs: initial link is rejected with Needs attention. Correct the original title/description to one distinct ID, then commit an update to the same branch. Editing text alone does not move it to review in this version. Retrying an old payload does not fetch newly edited GitHub text.
- Reminders: configure delay in project Settings. One delayed reminder per review round; new commits can begin another round. These are in-app notifications, not email.
- Worker stopped: receiver can still save pending events; restarting worker processes them. If receiver/tunnel was offline, use GitHub Recent Deliveries to redeliver missed events once the connection is restored.

## 8. Stop, troubleshoot and back up

To stop: Ctrl+C in each terminal. To restart another day, use section 3 and update webhook hostnames in section 4. Keep the laptop awake for live automation.

- Website cannot be reached: check Terminal 1 is running on port 8000.
- Port already in use: check your old terminals; do not start a second copy on the same port.
- No module named django: use .venv\Scripts\python.exe and reinstall requirements in the NEW environment.
- Missing tasks: stop and check .local\teamflow.sqlite3 was copied; make sure you opened the correct project folder and selected the correct project. Do not seed demo records to fix this.
- Worker not reporting: start Terminal 2; refresh the status page.
- PR not updating: check fresh tunnel URL, correct repository/webhook path/secret, task ID, worker and delivery result.
- SQLite writes failing: check free disk space and logs. Do not delete the database.

Repeat the verified local backup/restore test from the project folder:

```powershell
.\.venv\Scripts\python.exe manage.py verify_sqlite_backup
```

It creates a timestamped folder under .local\backups with backup.sqlite3, a separate restored-test.sqlite3 and verification.json. It checks integrity, foreign keys, schema and all table-content hashes. It never replaces the live database.

Keep a backup on another drive too; local copies do not protect against drive failure. To recover for real: stop all application processes, preserve the current database and SQLite sidecar files, and restore a verified backup in a clean separate project copy before switching to it. Never overwrite a database while the app is running. Remember changes after the backup time are not in that backup.

## Scope and verification

Existing local app workflows and automated tests were checked in the original location. Your new-folder setup must still be verified by following this guide. Hosting is deferred; real email is skipped; PostgreSQL is not used. You do not need ChatGPT to run the program. Do not publish .local, secrets or database backups. Code and these instructions are separate from hosted GitHub demo repositories, which do not automatically back up the Teamflow database.
