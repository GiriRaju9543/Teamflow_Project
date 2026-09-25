import secrets
import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models

def webhook_secret():
    return secrets.token_urlsafe(32)

class Workspace(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Membership(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=12, choices=[('leader', 'Team leader'), ('member', 'Team member')], default='member')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')]

class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=100)
    repository = models.CharField(max_length=180, blank=True, null=True, unique=True,
        validators=[RegexValidator(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$', 'Use owner/repository, for example giri/teamflow-demo.')])
    webhook_secret = models.CharField(max_length=100, default=webhook_secret, editable=False)
    reminder_minutes = models.PositiveIntegerField(default=1440, validators=[MinValueValidator(1), MaxValueValidator(43200)])
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class Task(models.Model):
    STATUSES = [('todo', 'Not started'), ('progress', 'In progress'), ('review', 'Waiting for review'), ('done', 'Completed'), ('changes', 'Changes requested')]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, max_length=6000)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assigned_tasks')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='review_tasks')
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_tasks')
    status = models.CharField(max_length=10, choices=STATUSES, default='todo')
    review_state = models.CharField(max_length=24, blank=True)
    due_date = models.DateField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    review_cycle = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-id']
    @property
    def key(self): return f'TASK-{self.pk}'
    def __str__(self): return f'{self.key} {self.title}'

class Activity(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activities')
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at', '-id']

class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    text = models.CharField(max_length=300)
    unique_key = models.CharField(max_length=200, unique=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-created_at']

class GitHubIdentity(models.Model):
    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name='github_identity')
    login = models.CharField(max_length=100)

class PullRequest(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    number = models.PositiveIntegerField()
    task = models.OneToOneField(Task, on_delete=models.CASCADE, related_name='pull_request')
    url = models.URLField()
    head_sha = models.CharField(max_length=64, blank=True)
    last_event_at = models.DateTimeField(null=True)
    merged = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['project', 'number'], name='unique_repository_pr')]

class Delivery(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='deliveries')
    delivery_id = models.CharField(max_length=100)
    event = models.CharField(max_length=80)
    payload = models.JSONField()
    state = models.CharField(max_length=12, default='pending')
    result = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)
    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['project', 'delivery_id'], name='unique_delivery')]

class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    last_seen = models.DateTimeField()
