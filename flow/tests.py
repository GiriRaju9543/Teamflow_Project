import hashlib
import hmac
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import Activity, Delivery, GitHubIdentity, Membership, Notification, Project, Task, Workspace
from .services import process_delivery, run_once

class WorkflowTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.leader = U.objects.create_user('giri', password='Testing-Login-593!')
        self.dev = U.objects.create_user('anu', password='Testing-Login-593!')
        self.reviewer = U.objects.create_user('ravi', password='Testing-Login-593!')
        self.other = U.objects.create_user('outsider', password='Testing-Login-593!')
        self.team = Workspace.objects.create(name='Our team')
        for u in [self.leader, self.dev, self.reviewer]:
            m = Membership.objects.create(workspace=self.team, user=u, role='leader' if u == self.leader else 'member')
            if u == self.reviewer: GitHubIdentity.objects.create(membership=m, login='ravi-github')
        self.project = Project.objects.create(workspace=self.team, name='Project', repository='giri/test', reminder_minutes=1)
        self.task = Task.objects.create(project=self.project, title='Login', assignee=self.dev, reviewer=self.reviewer, creator=self.leader)
        self.client.force_login(self.leader)
    def payload(self, action='opened', **kwargs):
        raw = {'number': 1, 'title': self.task.key + ' Build login', 'body': '', 'updated_at': timezone.now().isoformat(),
            'head': {'sha': 'abc123'}, 'draft': False, 'merged': False}
        raw.update(kwargs)
        return {'repository': {'full_name': 'giri/test'}, 'action': action, 'pull_request': raw}
    def deliver(self, payload, key='delivery-1', event='pull_request'):
        body = json.dumps(payload).encode()
        sig = 'sha256=' + hmac.new(self.project.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(reverse('webhook', args=[self.project.pk]), data=body, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=sig, HTTP_X_GITHUB_DELIVERY=key, HTTP_X_GITHUB_EVENT=event)
    def test_pages_and_opening_does_not_start(self):
        Activity.objects.create(project=self.project, task=self.task, text='Automatic update', actor=None)
        self.assertContains(self.client.get(reverse('activity')), 'Automation')
        self.assertContains(self.client.get(reverse('task_detail', args=[self.task.pk])), 'Automation')
        for name in ['board', 'teams', 'activity', 'reports', 'notifications', 'integrations']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertEqual(self.client.get(reverse('task_detail', args=[self.task.pk])).status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'todo')
    def test_anonymous_and_cross_team_denied(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('board')).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('task_detail', args=[self.task.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('start_task', args=[self.task.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('reports')), 'Login')
    def test_start_is_explicit_authorized_post(self):
        self.client.force_login(self.reviewer)
        self.assertEqual(self.client.post(reverse('start_task', args=[self.task.pk])).status_code, 403)
        self.client.force_login(self.dev)
        self.assertEqual(self.client.get(reverse('start_task', args=[self.task.pk])).status_code, 405)
        self.client.post(reverse('start_task', args=[self.task.pk]))
        self.client.post(reverse('start_task', args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'progress')
        self.assertEqual(Activity.objects.filter(task=self.task).count(), 1)
    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.dev)
        self.assertEqual(client.post(reverse('start_task', args=[self.task.pk])).status_code, 403)
    def test_task_creation_scopes_people(self):
        data = {'title': 'New task', 'description': '', 'assignee': self.other.pk, 'reviewer': self.reviewer.pk}
        response = self.client.post(reverse('task_new', args=[self.project.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 1)
        data['assignee'] = self.dev.pk
        response = self.client.post(reverse('task_new', args=[self.project.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Task.objects.get(title='New task').status, 'todo')
    def test_bad_signature_and_repository(self):
        self.assertEqual(self.client.post(reverse('webhook', args=[self.project.pk]), data='{}', content_type='application/json').status_code, 403)
        p = self.payload(); p['repository']['full_name'] = 'someone/else'
        self.assertEqual(self.deliver(p).status_code, 400)
        self.assertEqual(Delivery.objects.count(), 0)
    def test_duplicate_is_safe_and_merge_completes(self):
        p = self.payload()
        self.assertEqual(self.deliver(p).status_code, 202)
        self.assertEqual(self.deliver(p).status_code, 200)
        run_once(); run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'review')
        self.assertEqual(Delivery.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.deliver(self.payload('closed', merged=True), key='merge'); run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'done')
    def test_unmerged_and_draft_not_complete(self):
        self.deliver(self.payload('opened', draft=True)); run_once()
        self.task.refresh_from_db(); self.assertEqual(self.task.status, 'progress')
        self.deliver(self.payload('closed'), key='closed'); run_once()
        self.task.refresh_from_db(); self.assertEqual(self.task.status, 'progress')
        self.assertEqual(self.task.review_state, 'closed_unmerged')
    def test_review_approval_and_changes(self):
        self.deliver(self.payload()); run_once()
        p = self.payload('submitted')
        p['review'] = {'submitted_at': timezone.now().isoformat(), 'user': {'login': 'ravi-github'}, 'commit_id': 'abc123', 'state': 'approved'}
        self.deliver(p, key='approved', event='pull_request_review'); run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'review'); self.assertEqual(self.task.review_state, 'approved')
        self.assertIsNone(self.task.review_started_at)
        p['review']['state'] = 'changes_requested'; p['review']['submitted_at'] = timezone.now().isoformat()
        self.deliver(p, key='changes', event='pull_request_review'); run_once()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'changes'); self.assertEqual(self.task.review_state, 'changes_requested')
    def test_reminder_once_and_cancellation(self):
        self.task.status='review'; self.task.review_started_at=timezone.now()-timedelta(minutes=5); self.task.review_cycle=1; self.task.save()
        self.assertEqual(run_once(), 1); self.assertEqual(run_once(), 0)
        self.task.status='done'; self.task.save()
        self.assertEqual(run_once(), 0)
    def test_unknown_task_and_late_event(self):
        p=self.payload(); p['pull_request']['title']='TASK-999999 wrong'
        self.deliver(p); run_once()
        self.assertEqual(Delivery.objects.first().state, 'attention')
        self.deliver(self.payload(), key='valid'); run_once()
        self.deliver(self.payload('converted_to_draft', updated_at=(timezone.now()-timedelta(days=1)).isoformat()), key='old'); run_once()
        self.task.refresh_from_db(); self.assertEqual(self.task.status, 'review')
    def test_logout_post_and_signup(self):
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.client.post(reverse('logout'))
        self.assertEqual(self.client.get(reverse('signup')).status_code, 200)
    def test_csv_formula_is_escaped(self):
        self.task.title='=1+1';self.task.save()
        response=self.client.get(reverse('reports')+'?download=csv')
        self.assertIn("'=1+1",response.content.decode())
