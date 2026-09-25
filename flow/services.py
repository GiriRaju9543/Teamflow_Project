"""Database-backed GitHub processing and restart-safe in-app reminders."""
import re
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import Activity, Delivery, GitHubIdentity, Notification, PullRequest, Task, WorkerHeartbeat

def notify(task, user, text, key):
    Notification.objects.get_or_create(unique_key=key, defaults={'user': user, 'task': task, 'text': text})

def transition(task, status, detail, review_state='', at=None):
    now = timezone.now()
    if status == 'review' and (task.status != 'review' or task.review_state != review_state):
        if review_state != 'approved':
            task.review_cycle += 1
            task.review_started_at = now
    task.status = status
    task.review_state = review_state
    if status != 'review' or review_state == 'approved':
        task.review_started_at = None
    task.completed_at = now if status == 'done' else None
    task.save()
    Activity.objects.create(project=task.project, task=task, text=detail)

def _apply(delivery):
    data = delivery.payload
    if delivery.event == 'ping': return 'done', 'Connection check received.'
    if delivery.event not in ('pull_request', 'pull_request_review'):
        return 'ignored', 'Event not used by this application.'
    raw = data.get('pull_request')
    if not isinstance(raw, dict): return 'attention', 'Missing pull request.'
    number = raw.get('number') or data.get('number')
    if not isinstance(number, int) or number < 1: return 'attention', 'Invalid pull request number.'
    pr = PullRequest.objects.select_for_update().filter(project=delivery.project, number=number).first()
    if pr:
        task = Task.objects.select_for_update().get(pk=pr.task_id)
    else:
        ids = set(re.findall(r'\bTASK-(\d+)\b', (raw.get('title') or '') + '\n' + (raw.get('body') or ''), re.I))
        if len(ids) != 1: return 'attention', 'Include exactly one TASK-ID in the pull request title or description.'
        task = Task.objects.select_for_update().filter(project=delivery.project, pk=int(next(iter(ids)))).first()
        if not task: return 'attention', 'Task does not belong to this project.'
        if PullRequest.objects.filter(task=task).exists(): return 'attention', 'Task already has a linked pull request.'
        pr = PullRequest.objects.create(project=delivery.project, number=number, task=task,
            url=f'https://github.com/{delivery.project.repository}/pull/{number}')
    if pr.merged:
        return 'ignored', 'Merged pull request is already complete.'
    review = data.get('review') or {}
    stamp = (review.get('submitted_at') if delivery.event == 'pull_request_review' else raw.get('updated_at'))
    at = parse_datetime(stamp or '')
    if not at or timezone.is_naive(at): return 'attention', 'Missing or invalid event timestamp.'
    if pr.last_event_at and at < pr.last_event_at:
        return 'ignored', 'Older event ignored to preserve current status.'
    action = data.get('action', '')
    sha = (raw.get('head') or {}).get('sha', '')
    if not isinstance(sha, str) or len(sha) > 64: return 'attention', 'Invalid commit identifier.'
    if delivery.event == 'pull_request_review':
        identity = GitHubIdentity.objects.filter(membership__user=task.reviewer,
            membership__workspace=task.project.workspace).first()
        author = (review.get('user') or {}).get('login', '')
        if not identity or author.lower() != identity.login.lower():
            return 'attention', 'Review author is not the mapped assigned reviewer.'
        if review.get('commit_id') != sha or (pr.head_sha and pr.head_sha != sha):
            return 'ignored', 'Review is for an older commit.'
        if action == 'dismissed':
            transition(task, 'review', 'GitHub approval was dismissed; review is needed again.')
        elif action == 'submitted' and review.get('state') == 'approved':
            transition(task, 'review', 'Assigned reviewer approved the changes. Waiting for a human merge.', 'approved')
        elif action == 'submitted' and review.get('state') == 'changes_requested':
            transition(task, 'changes', 'Assigned reviewer requested corrections.', 'changes_requested')
            notify(task, task.assignee, f'{task.key}: changes requested.', f'corrections:{delivery.pk}')
        else: return 'ignored', 'Informational review does not change task status.'
    elif action == 'closed':
        if raw.get('merged') is True:
            transition(task, 'done', 'GitHub pull request merged. Task completed.')
            pr.merged = True
        else:
            transition(task, 'progress', 'Pull request closed without merging. Task needs attention.', 'closed_unmerged')
    elif action in ('opened', 'reopened', 'ready_for_review', 'synchronize', 'converted_to_draft'):
        if raw.get('draft') or action == 'converted_to_draft':
            transition(task, 'progress', 'GitHub pull request is a draft; work is still in progress.', 'draft')
        else:
            # A new commit starts a fresh review cycle even when already waiting.
            if action == 'synchronize' and sha != pr.head_sha:
                task.review_started_at = None
                task.review_state = 'new_commit'
            transition(task, 'review', 'GitHub changes are ready for review.')
            notify(task, task.reviewer, f'{task.key} is ready for your review.', f'review:{task.pk}:{task.review_cycle}')
    else: return 'ignored', 'Pull request action does not change the workflow.'
    pr.head_sha = sha
    pr.last_event_at = at
    pr.save()
    return 'done', f'{task.key} updated.'

def process_delivery(pk):
    try:
        with transaction.atomic():
            delivery = Delivery.objects.select_for_update().select_related('project__workspace').get(pk=pk)
            if delivery.state != 'pending': return
            state, result = _apply(delivery)
            delivery.state, delivery.result = state, result
            delivery.attempts += 1
            delivery.processed_at = timezone.now()
            delivery.save()
    except Exception:
        # Roll back partial task changes; retain a durable, retryable error.
        Delivery.objects.filter(pk=pk, state='pending').update(state='failed', result='Processing failed. Check worker logs, then retry.')
        raise

def run_once():
    WorkerHeartbeat.objects.update_or_create(name='automation', defaults={'last_seen': timezone.now()})
    for pk in list(Delivery.objects.filter(state='pending').order_by('created_at').values_list('pk', flat=True)[:100]):
        try: process_delivery(pk)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Delivery %s failed', pk)
    sent = 0
    ids = Task.objects.filter(status='review', review_started_at__isnull=False).values_list('pk', flat=True)
    for pk in list(ids):
        with transaction.atomic():
            task = Task.objects.select_for_update().select_related('project', 'reviewer').get(pk=pk)
            if task.status != 'review' or not task.review_started_at or task.review_state == 'approved': continue
            if timezone.now() < task.review_started_at + timedelta(minutes=task.project.reminder_minutes): continue
            _, created = Notification.objects.get_or_create(unique_key=f'reminder:{pk}:{task.review_cycle}',
                defaults={'user': task.reviewer, 'task': task, 'text': f'Reminder: {task.key} is waiting for your review.'})
            if created:
                sent += 1
                Activity.objects.create(project=task.project, task=task, text='Review reminder created for the assigned reviewer.')
    return sent
