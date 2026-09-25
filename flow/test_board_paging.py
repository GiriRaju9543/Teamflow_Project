from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Task, Project, Workspace, Membership

class BoardPagingTests(TestCase):
    def test_large_board_paging_filters_and_counts(self):
        user = get_user_model().objects.create_user('paging-user')
        team = Workspace.objects.create(name='Paging team')
        Membership.objects.create(user=user, workspace=team, role='leader')
        project = Project.objects.create(workspace=team, name='Paging project')
        Task.objects.bulk_create([Task(project=project, title=f'Item {i}', assignee=user, reviewer=user, creator=user) for i in range(1000)])
        self.client.force_login(user)
        response = self.client.get('/')
        column = response.context['columns'][0]
        self.assertEqual(response.context['task_total'], 1000)
        self.assertEqual(column['total'], 1000)
        first = {t.pk for t in column['tasks']}
        self.assertEqual(len(first), 10)
        self.assertContains(response, 'Next')
        response = self.client.get(column['next_url'])
        self.assertFalse(first & {t.pk for t in response.context['columns'][0]['tasks']})
        response = self.client.get('/', {'q':'Item 99', 'mine':'1'})
        column = response.context['columns'][0]
        self.assertEqual(column['total'], 11)
        self.assertIn('mine=1', column['next_url'])
        response = self.client.get('/', {'page_todo':'invalid'})
        self.assertEqual(response.context['columns'][0]['page'].number, 1)
        task = Task.objects.first()
        response = self.client.get('/', {'q':task.key})
        self.assertEqual(response.context['columns'][0]['total'], 1)

    def test_selected_project_survives_return_to_board(self):
        user = get_user_model().objects.create_user('selector')
        team = Workspace.objects.create(name='Team')
        Membership.objects.create(user=user, workspace=team)
        first = Project.objects.create(workspace=team, name='A project')
        selected = Project.objects.create(workspace=team, name='Z project')
        self.client.force_login(user)
        self.client.get('/', {'project': str(selected.pk)})
        self.assertEqual(self.client.get('/').context['project'], selected)
        self.assertEqual(self.client.get('/', {'project': str(first.pk)}).context['project'], first)
        self.assertEqual(self.client.get('/').context['project'], first)
        first.delete()
        self.assertEqual(self.client.get('/').context['project'], selected)
