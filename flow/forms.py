from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from .models import Task, Project, Workspace

class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ['username', 'first_name', 'email']

class WorkspaceForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = ['name']

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'repository', 'reminder_minutes']
        labels = {'repository': 'GitHub repository (optional for now)', 'reminder_minutes': 'Review reminder delay (minutes)'}
        help_texts = {'repository': 'Use owner/repository. Leave blank until you connect GitHub.', 'reminder_minutes': '1440 minutes = 24 hours. Use a shorter delay only for testing.'}
    def clean_repository(self):
        return (self.cleaned_data.get('repository') or '').strip().lower() or None

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'assignee', 'reviewer', 'due_date']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'due_date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        users = get_user_model().objects.filter(memberships__workspace=project.workspace).distinct()
        self.fields['assignee'].queryset = users
        self.fields['reviewer'].queryset = users
    def clean(self):
        data = super().clean()
        if data.get('assignee') and data.get('assignee') == data.get('reviewer'):
            raise forms.ValidationError('Choose a different teammate to review this task.')
        return data

class MemberForm(forms.Form):
    username = forms.CharField(max_length=150, help_text='The person must first create an account on this application.')
    role = forms.ChoiceField(choices=[('member', 'Team member'), ('leader', 'Team leader')])

class RequestChangesForm(forms.Form):
    reason = forms.CharField(max_length=250, label='What needs to change?',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Explain the correction so your teammate knows what to fix.'}))

class IdentityForm(forms.Form):
    login = forms.RegexField(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$', max_length=39, label='Your GitHub username')
