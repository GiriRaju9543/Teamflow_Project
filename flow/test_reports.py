from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Workspace, Membership, Project, Task

class ReportTests(TestCase):
    def test_metrics_filter_export_and_isolation(self):
        user = get_user_model().objects.create_user('reporter')
        team = Workspace.objects.create(name='Team')
        Membership.objects.create(user=user, workspace=team)
        project = Project.objects.create(workspace=team, name='Visible')
        other_team = Workspace.objects.create(name='Other')
        hidden = Project.objects.create(workspace=other_team, name='Hidden')
        second = Project.objects.create(workspace=team, name='Second')
        now = timezone.now()
        def task(project, **kw):
            return Task.objects.create(project=project, title='Example', assignee=user, reviewer=user, creator=user, **kw)
        task(project, status='review', review_started_at=now-timedelta(minutes=20), due_date=timezone.localdate()-timedelta(days=1))
        task(project, status='review', review_started_at=now-timedelta(minutes=40))
        task(project, status='review', review_state='approved')
        task(project, status='done', due_date=timezone.localdate()-timedelta(days=1))
        task(second, status='todo')
        task(hidden, status='todo')
        self.client.force_login(user)
        with patch('flow.views.timezone.now', return_value=now):
            response=self.client.get('/reports/', {'project':str(project.pk)})
        self.assertEqual(response.status_code,200)
        for key, value in [('total',4),('pending_count',2),('average_wait',30),('overdue',1),('completion_percent',25)]:
            self.assertEqual(response.context[key],value)
        self.assertEqual(self.client.get('/reports/').context['total'],5)
        self.assertEqual(self.client.get('/reports/',{'project':str(hidden.pk)}).status_code,404)
        csv=self.client.get('/reports/',{'project':str(project.pk),'download':'csv'}).content.decode()
        self.assertEqual(len(csv.splitlines()),5)
        Task.objects.filter(project=project).delete()
        response=self.client.get('/reports/',{'project':str(project.pk)})
        self.assertEqual(response.context['completion_percent'],0)
        self.assertIsNone(response.context['average_wait'])
