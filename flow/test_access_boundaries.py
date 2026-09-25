from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import Workspace, Membership, Project, Task, Delivery, Notification

class AccessBoundaryTests(TestCase):
    def setUp(self):
        U=get_user_model()
        self.leader=U.objects.create_user('owner')
        self.member=U.objects.create_user('developer')
        self.outside=U.objects.create_user('other-team')
        self.team=Workspace.objects.create(name='Private team')
        Membership.objects.create(user=self.leader,workspace=self.team,role='leader')
        Membership.objects.create(user=self.member,workspace=self.team)
        other=Workspace.objects.create(name='Other team')
        Membership.objects.create(user=self.outside,workspace=other,role='leader')
        self.project=Project.objects.create(workspace=self.team,name='Private project')
        self.task=Task.objects.create(project=self.project,title='Confidential task',assignee=self.member,reviewer=self.leader,creator=self.leader,status='review')
        self.delivery=Delivery.objects.create(project=self.project,delivery_id='private',event='ping',payload={},state='attention')
        Notification.objects.create(user=self.leader,task=self.task,text='Reviewer-only message',unique_key='private-notice')

    def test_outsider_direct_urls_and_reports(self):
        self.client.force_login(self.outside)
        for name,pk in [('task_detail',self.task.pk),('task_edit',self.task.pk),('request_changes',self.task.pk),('project_edit',self.project.pk),('task_new',self.project.pk),('members',self.team.pk)]:
            url=reverse(name,args=[pk])
            self.assertEqual(self.client.get(url).status_code,404,name)
            self.assertEqual(self.client.post(url,{'reason':'Unauthorized'}).status_code,404,name)
        self.assertEqual(self.client.post(reverse('retry_delivery',args=[self.delivery.pk])).status_code,404)
        for name in ['board','reports','deliveries']:
            self.assertEqual(self.client.get(reverse(name),{'project':str(self.project.pk)}).status_code,404)
        self.assertNotContains(self.client.get('/reports/?download=csv'),'Confidential task')
        self.task.refresh_from_db();self.assertEqual(self.task.status,'review')

    def test_member_cannot_manage_project_or_review_own_work(self):
        self.client.force_login(self.member)
        for name,pk in [('task_edit',self.task.pk),('project_edit',self.project.pk),('task_new',self.project.pk),('project_new',self.team.pk)]:
            url=reverse(name,args=[pk])
            self.assertEqual(self.client.get(url).status_code,403,name)
            self.assertEqual(self.client.post(url,{}).status_code,403,name)
        self.assertEqual(self.client.post(reverse('request_changes',args=[self.task.pk]),{'reason':'Self-review'}).status_code,403)
        self.assertNotContains(self.client.get('/integrations/'),self.project.webhook_secret)
        self.assertNotContains(self.client.get('/notifications/'),'Reviewer-only message')
        self.client.post('/notifications/')
        self.assertFalse(Notification.objects.get(unique_key='private-notice').read)

    def test_anonymous_redirects_and_wrong_password(self):
        for path in ['/','/reports/','/deliveries/','/integrations/',f'/tasks/{self.task.pk}/']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,302)
            self.assertTrue(response.url.startswith('/login/'))
        self.leader.set_password('Valid-for-test-492!');self.leader.save()
        self.client.post('/login/',{'username':'owner','password':'wrong'})
        self.assertNotIn('_auth_user_id',self.client.session)
