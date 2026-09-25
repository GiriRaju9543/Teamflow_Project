from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from .models import Workspace, Membership, Project, Task, Activity, Notification, Delivery, PullRequest
from .services import run_once


class CorrectionTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user('author')
        self.reviewer = get_user_model().objects.create_user('reviewer')
        self.leader = get_user_model().objects.create_user('leader')
        self.team = Workspace.objects.create(name='Team')
        for user in [self.author, self.reviewer, self.leader]:
            Membership.objects.create(workspace=self.team, user=user, role='leader' if user == self.leader else 'member')
        self.project = Project.objects.create(workspace=self.team, name='Project', repository='test/demo', reminder_minutes=1)
        self.task = Task.objects.create(project=self.project, title='Fix page', assignee=self.author,
            reviewer=self.reviewer, creator=self.leader, status='review', review_cycle=1, review_started_at=timezone.now())
        self.url = reverse('request_changes', args=[self.task.pk])
        self.client.force_login(self.reviewer)

    def test_required_reason_and_assigned_reviewer_only(self):
        response = self.client.post(self.url, {'reason': '  '})
        self.assertContains(response, 'This field is required.')
        self.task.refresh_from_db(); self.assertEqual(self.task.status, 'review')
        for user in [self.author, self.leader]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {'reason': 'Fix it'}).status_code, 403)
        self.assertEqual(Notification.objects.count(), 0)

    def test_correction_once_stops_reminders_and_updates_board(self):
        for _ in range(2):
            self.assertEqual(self.client.post(self.url, {'reason': 'Add the welcome text.'}).status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'changes'); self.assertIsNone(self.task.review_started_at)
        self.assertEqual(Notification.objects.filter(user=self.author).count(), 1)
        self.assertEqual(Activity.objects.filter(actor=self.reviewer).count(), 1)
        self.assertEqual(run_once(), 0)
        response = self.client.get(reverse('board'))
        self.assertEqual(len(response.context['columns']), 5)
        self.assertEqual(response.context['columns'][-1]['tasks'][0].pk, self.task.pk)
        self.assertEqual(response.context['in_progress'], 0)
        self.assertEqual(response.context['waiting'], 0)
        self.assertContains(response, 'Not started'); self.assertContains(response, 'Changes requested')

    def test_new_commit_returns_to_review_and_new_cycle(self):
        PullRequest.objects.create(project=self.project, task=self.task, number=1,
            url='https://github.com/test/demo/pull/1', head_sha='old', last_event_at=timezone.now())
        self.client.post(self.url, {'reason': 'Fix welcome text.'})
        Delivery.objects.create(project=self.project, delivery_id='new-commit', event='pull_request', payload={
            'action': 'synchronize', 'pull_request': {'number': 1, 'head': {'sha': 'new'},
            'updated_at': timezone.now().isoformat(), 'draft': False}})
        run_once(); self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'review'); self.assertEqual(self.task.review_cycle, 2)
        self.assertIsNotNone(self.task.review_started_at)
        self.assertTrue(Notification.objects.filter(user=self.reviewer).exists())
        self.client.post(self.url, {'reason': 'One more correction.'})
        self.assertEqual(Notification.objects.filter(user=self.author).count(), 2)
