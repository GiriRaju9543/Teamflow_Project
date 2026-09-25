"""Create a consistent SQLite backup and verify a separate restored copy."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def fingerprint(connection):
    integrity = connection.execute('PRAGMA integrity_check').fetchall()
    if integrity != [('ok',)]:
        raise CommandError('Database integrity check failed.')
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise CommandError('Database foreign-key check failed.')
    schema = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name").fetchall()
    counts, hashes = {}, {}
    for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = connection.execute('SELECT * FROM ' + quoted)
        # Hash every field without writing private row contents into the report.
        values = sorted(hashlib.sha256(repr(tuple(row)).encode()).hexdigest() for row in rows)
        counts[name] = len(values)
        hashes[name] = hashlib.sha256(''.join(values).encode()).hexdigest()
    return {'schema_sha256': hashlib.sha256(repr(schema).encode()).hexdigest(),
            'table_counts': counts, 'table_sha256': hashes}


class Command(BaseCommand):
    help = 'Back up SQLite and verify a separate restored copy; never replaces the live database.'

    def handle(self, *args, **options):
        config = settings.DATABASES['default']
        if config['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('This command supports SQLite only.')
        source = Path(config['NAME']).resolve()
        if not source.is_file():
            raise CommandError('The live SQLite database was not found.')
        run = Path(settings.LOCAL_DIR) / 'backups' / ('verified-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
        run.mkdir(parents=True, exist_ok=False)
        backup = run / 'backup.sqlite3'
        restored = run / 'restored-test.sqlite3'
        # SQLite's backup API captures a consistent snapshot even while the app is running.
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as live, sqlite3.connect(str(backup)) as saved:
            live.backup(saved)
        with sqlite3.connect(backup.as_uri() + '?mode=ro', uri=True) as saved, sqlite3.connect(str(restored)) as recovered:
            expected = fingerprint(saved)
            saved.backup(recovered)
            actual = fingerprint(recovered)
        if actual != expected:
            raise CommandError('Restored records differ from the backup. Do not use this copy.')
        report = {'verified_at_utc': datetime.now(timezone.utc).isoformat(),
                  'source': str(source), 'backup': str(backup), 'restored_test': str(restored),
                  'result': 'PASS', 'checks': ['SQLite integrity', 'foreign keys', 'schema equality', 'all table row counts and content hashes'],
                  **actual,
                  'limitations': ['Local copies only; no protection from loss of this drive.',
                                 'Database recovery verified; full server or external GitHub recovery not simulated.',
                                 'Keep application code and required configuration separately.']}
        (run / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('PASS: backup restored to a separate database; all table contents match.'))
        self.stdout.write(f'Backup folder: {run}')
        self.stdout.write('Live database was opened read-only. No worker was started against the restored copy.')
        for table in ['auth_user','flow_project','flow_task','flow_activity','flow_notification','flow_delivery','flow_pullrequest']:
            self.stdout.write(f'{table}: {actual["table_counts"].get(table, 0)} records')
