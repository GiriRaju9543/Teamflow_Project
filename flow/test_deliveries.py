from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Workspace, Membership, Project, Delivery

class DeliveryPageTests(TestCase):
    def test_filter_pagination_permissions_and_retry(self):
        user=get_user_model().objects.create_user('leader')
        team=Workspace.objects.create(name='Team')
        membership=Membership.objects.create(user=user,workspace=team,role='leader')
        project=Project.objects.create(workspace=team,name='One')
        second=Project.objects.create(workspace=team,name='Two')
        for i in range(31):
            Delivery.objects.create(project=project,delivery_id=str(i),event='ping',payload={},state='attention')
        Delivery.objects.create(project=second,delivery_id='other',event='ping',payload={})
        self.client.force_login(user)
        response=self.client.get('/deliveries/',{'project':str(project.pk)})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['page'].paginator.count,31)
        self.assertEqual(len(response.context['deliveries']),30)
        self.assertIn(str(project.pk),response.context['next_url'])
        self.assertEqual(len(self.client.get('/deliveries/' + response.context['next_url']).context['deliveries']),1)
        self.assertNotContains(self.client.get('/integrations/'), 'Queued events are processed')
        item=Delivery.objects.filter(project=project).first()
        self.assertRedirects(self.client.post(f'/deliveries/{item.pk}/retry/'),f'/deliveries/?project={project.pk}')
        membership.role='member';membership.save()
        self.assertEqual(self.client.get('/deliveries/').context['page'].paginator.count,0)
        self.assertEqual(self.client.get('/deliveries/',{'project':str(project.pk)}).status_code,404)
        self.assertEqual(self.client.post(f'/deliveries/{item.pk}/retry/').status_code,403)

