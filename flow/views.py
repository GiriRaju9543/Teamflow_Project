import csv
import hashlib
import hmac
import json
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, RequestDataTooBig
from django.db import transaction
from django.db.models import Count, Q, Value, CharField
from django.db.models.functions import Cast, Concat
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .forms import IdentityForm, MemberForm, ProjectForm, SignupForm, TaskForm, WorkspaceForm, RequestChangesForm
from .models import Activity, Delivery, GitHubIdentity, Membership, Notification, Project, Task, WorkerHeartbeat, Workspace

def projects_for(user):
    return Project.objects.filter(workspace__memberships__user=user).distinct().select_related('workspace').order_by('name')

def is_leader(user, workspace):
    return Membership.objects.filter(user=user, workspace=workspace, role='leader').exists()

def leader_required(user, workspace):
    if not is_leader(user, workspace): raise PermissionDenied

def project_context(request):
    projects = projects_for(request.user)
    selected = request.GET.get('project')
    if selected:
        project = get_object_or_404(projects, pk=selected)
    else:
        saved = request.session.get('board_project')
        project = projects.filter(pk=saved).first() if saved else None
        if project is None:
            project = projects.first()
    if project:
        request.session['board_project'] = str(project.pk)
    else:
        request.session.pop('board_project', None)
    return projects, project

def signup(request):
    if request.user.is_authenticated: return redirect('board')
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
            workspace = Workspace.objects.create(name=f'{user.first_name or user.username}’s team')
            Membership.objects.create(workspace=workspace, user=user, role='leader')
        login(request, user)
        return redirect('project_new', workspace_id=workspace.pk)
    return render(request, 'signup.html', {'form': form})

@login_required
def board(request):
    projects, project = project_context(request)
    tasks = Task.objects.filter(project=project).select_related('assignee', 'reviewer') if project else Task.objects.none()
    counts = dict(tasks.order_by().values('status').annotate(total=Count('id')).values_list('status', 'total'))
    query = request.GET.get('q', '').strip()
    mine = request.GET.get('mine') == '1'
    visible = tasks
    if query:
        visible = visible.annotate(search_key=Concat(Value('TASK-'), Cast('id', CharField()))).filter(Q(title__icontains=query) | Q(search_key__icontains=query))
    if mine:
        visible = visible.filter(assignee=request.user)
    columns = []
    for code, label in Task.STATUSES:
        page = Paginator(visible.filter(status=code), 10).get_page(request.GET.get('page_' + code))
        def page_url(number):
            params = request.GET.copy()
            params['page_' + code] = number
            return '?' + params.urlencode()
        columns.append({'code': code, 'label': label, 'tasks': page.object_list,
            'total': page.paginator.count, 'page': page,
            'previous_url': page_url(page.previous_page_number()) if page.has_previous() else '',
            'next_url': page_url(page.next_page_number()) if page.has_next() else ''})
    return render(request, 'board.html', {'projects': projects, 'project': project, 'columns': columns, 'query': query,
        'mine': mine, 'task_total': sum(counts.values()), 'completed': counts.get('done', 0),
        'not_started': counts.get('todo', 0), 'in_progress': counts.get('progress', 0),
        'waiting': counts.get('review', 0), 'overdue': tasks.filter(due_date__lt=timezone.localdate()).exclude(status='done').count(),
        'leader': bool(project and is_leader(request.user, project.workspace)), 'today': timezone.localdate()})


@login_required
def teams(request):
    form = WorkspaceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            workspace = form.save()
            Membership.objects.create(workspace=workspace, user=request.user, role='leader')
        return redirect('project_new', workspace_id=workspace.pk)
    return render(request, 'teams.html', {'form': form})

@login_required
def members(request, pk):
    membership = get_object_or_404(Membership, workspace_id=pk, user=request.user)
    form = MemberForm(request.POST if request.POST.get('action') == 'member' else None)
    identity = GitHubIdentity.objects.filter(membership=membership).first()
    identity_form = IdentityForm(request.POST if request.POST.get('action') == 'identity' else None,
        initial={'login': identity.login if identity else ''})
    if request.method == 'POST':
        if request.POST.get('action') == 'identity' and identity_form.is_valid():
            GitHubIdentity.objects.update_or_create(membership=membership, defaults={'login': identity_form.cleaned_data['login']})
            messages.success(request, 'GitHub username saved. Only map an account you control.')
            return redirect('members', pk=pk)
        elif request.POST.get('action') == 'member':
            leader_required(request.user, membership.workspace)
            if form.is_valid():
                user = get_user_model().objects.filter(username=form.cleaned_data['username']).first()
                if not user: form.add_error('username', 'No account with that username. Ask them to register first.')
                else:
                    _, created = Membership.objects.get_or_create(workspace=membership.workspace, user=user, defaults={'role': form.cleaned_data['role']})
                    messages.success(request, 'Member added.' if created else 'That person is already a member; existing permissions unchanged.')
                    return redirect('members', pk=pk)
    return render(request, 'members.html', {'form': form, 'identity_form': identity_form, 'workspace': membership.workspace,
        'people': membership.workspace.memberships.select_related('user'), 'leader': membership.role == 'leader'})

@login_required
def project_edit(request, pk=None, workspace_id=None):
    project = get_object_or_404(projects_for(request.user), pk=pk) if pk else None
    workspace = project.workspace if project else get_object_or_404(Workspace, pk=workspace_id, memberships__user=request.user)
    leader_required(request.user, workspace)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        if project and Project.objects.get(pk=project.pk).repository != saved.repository and project.pullrequest_set.exists():
            form.add_error('repository', 'This project already has linked pull requests. Create a separate project for a different repository.')
        else:
            saved.workspace = workspace
            saved.save()
            messages.success(request, 'Project saved.')
            return redirect(reverse('board') + f'?project={saved.pk}')
    return render(request, 'form.html', {'form': form, 'title': 'Project settings' if pk else 'Create a project', 'subtitle': workspace.name, 'button': 'Save project'})

@login_required
def task_edit(request, pk):
    editing = request.resolver_match.url_name == 'task_edit'
    task = get_object_or_404(Task, pk=pk, project__in=projects_for(request.user)) if editing else None
    project = task.project if task else get_object_or_404(projects_for(request.user), pk=pk)
    leader_required(request.user, project.workspace)
    form = TaskForm(request.POST or None, instance=task, project=project)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            previous = Task.objects.get(pk=task.pk) if task else None
            saved = form.save(commit=False)
            saved.project = project
            if not task: saved.creator = request.user
            if previous and previous.reviewer_id != saved.reviewer_id and saved.status == 'review':
                saved.review_state = ''
                saved.review_cycle += 1
                saved.review_started_at = timezone.now()
            saved.save()
            Activity.objects.create(project=project, task=saved, actor=request.user, text='Task updated.' if task else 'Task assigned. Work has not started.')
        messages.success(request, 'Task saved.')
        return redirect('task_detail', pk=saved.pk)
    return render(request, 'form.html', {'form': form, 'title': 'Edit task' if task else 'Create a task', 'subtitle': project.name, 'button': 'Save task'})

@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.select_related('project__workspace', 'assignee', 'reviewer'), pk=pk, project__in=projects_for(request.user))
    leader = is_leader(request.user, task.project.workspace)
    return render(request, 'task.html', {'task': task, 'leader': leader,
        'can_request_changes': task.status == 'review' and task.reviewer_id == request.user.pk and task.assignee_id != request.user.pk,
        'can_start': task.status == 'todo' and (leader or task.assignee_id == request.user.pk), 'history': task.activities.select_related('actor')})

@login_required
@require_POST
def start_task(request, pk):
    with transaction.atomic():
        task = get_object_or_404(Task.objects.select_for_update(), pk=pk, project__in=projects_for(request.user))
        if request.user.pk != task.assignee_id and not is_leader(request.user, task.project.workspace): raise PermissionDenied
        if task.status == 'todo':
            task.status = 'progress'
            task.save()
            Activity.objects.create(project=task.project, task=task, actor=request.user, text='Started work on the task.')
            messages.success(request, 'Task moved to In progress.')
    return redirect('task_detail', pk=pk)

@login_required
def request_changes(request, pk):
    task = get_object_or_404(Task, pk=pk, project__in=projects_for(request.user))
    if request.user.pk != task.reviewer_id or request.user.pk == task.assignee_id:
        raise PermissionDenied
    form = RequestChangesForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            task = get_object_or_404(Task.objects.select_for_update(), pk=pk, project__in=projects_for(request.user))
            if request.user.pk != task.reviewer_id or request.user.pk == task.assignee_id:
                raise PermissionDenied
            if task.status != 'review':
                messages.info(request, 'This task is no longer waiting for review. No additional request was sent.')
                return redirect('task_detail', pk=pk)
            reason = form.cleaned_data['reason']
            task.status = 'changes'
            task.review_state = 'changes_requested'
            task.review_started_at = None
            task.completed_at = None
            task.save()
            Activity.objects.create(project=task.project, task=task, actor=request.user,
                text=f'Changes requested in Teamflow: {reason}')
            Notification.objects.get_or_create(unique_key=f'manual-corrections:{task.pk}:{task.review_cycle}',
                defaults={'user': task.assignee, 'task': task, 'text': f'{task.key}: changes requested. {reason}'})
        messages.success(request, 'Changes requested. Your teammate has been notified; the GitHub pull request stays open.')
        return redirect('task_detail', pk=pk)
    if task.status != 'review':
        messages.info(request, 'Changes can only be requested while a task is waiting for review.')
        return redirect('task_detail', pk=pk)
    return render(request, 'form.html', {'form': form, 'title': 'Request changes',
        'subtitle': f'{task.key} · {task.title}. This records your review in Teamflow.', 'button': 'Request changes'})

@login_required
def notifications(request):
    items = Notification.objects.filter(user=request.user, task__project__in=projects_for(request.user))
    if request.method == 'POST':
        items.filter(read=False).update(read=True)
        return redirect('notifications')
    return render(request, 'notifications.html', {'items': items.select_related('task')[:100]})

@login_required
def activity(request):
    return render(request, 'activity.html', {'items': Activity.objects.filter(project__in=projects_for(request.user)).select_related('task', 'project', 'actor')[:100]})

@login_required
def reports(request):
    projects = projects_for(request.user)
    selected = request.GET.get('project', '')
    project = get_object_or_404(projects, pk=selected) if selected else None
    tasks = Task.objects.filter(project__in=projects).select_related('project', 'assignee', 'reviewer')
    if project:
        tasks = tasks.filter(project=project)
    if request.GET.get('download') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="teamflow-tasks.csv"'
        writer = csv.writer(response)
        writer.writerow(['Task', 'Title', 'Project', 'Assigned to', 'Status', 'Due date'])
        def safe(value):
            value = str(value)
            return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r')) else value
        for t in tasks: writer.writerow([t.key, safe(t.title), safe(t.project.name), safe(t.assignee.username), t.get_status_display(), t.due_date or ''])
        return response
    counts = dict(tasks.order_by().values('status').annotate(total=Count('id')).values_list('status', 'total'))
    now = timezone.now()
    pending = tasks.filter(status='review', review_started_at__isnull=False).exclude(review_state='approved')
    waits = [max(0, (now - started).total_seconds() / 60) for started in pending.values_list('review_started_at', flat=True)]
    waiting_page = Paginator(pending.order_by('review_started_at', 'pk'), 10).get_page(request.GET.get('waiting_page'))
    overdue_tasks = tasks.exclude(status='done').filter(due_date__lt=timezone.localdate())
    overdue_page = Paginator(overdue_tasks.order_by('due_date', 'pk'), 10).get_page(request.GET.get('overdue_page'))
    def page_links(page, key):
        def link(number):
            params = request.GET.copy()
            params[key] = number
            return '?' + params.urlencode()
        return {'previous': link(page.previous_page_number()) if page.has_previous() else '',
                'next': link(page.next_page_number()) if page.has_next() else ''}
    params = request.GET.copy()
    params['download'] = 'csv'
    total = sum(counts.values())
    return render(request, 'reports.html', {'rows': [(label, counts.get(code, 0)) for code, label in Task.STATUSES],
        'projects': projects, 'project': project, 'total': total, 'overdue': overdue_tasks.count(),
        'completed': counts.get('done', 0), 'completion_percent': round(100 * counts.get('done', 0) / total) if total else 0,
        'pending_count': len(waits), 'average_wait': round(sum(waits) / len(waits)) if waits else None,
        'waiting_page': waiting_page, 'overdue_page': overdue_page, 'now': now,
        'waiting_links': page_links(waiting_page, 'waiting_page'), 'overdue_links': page_links(overdue_page, 'overdue_page'),
        'download_url': '?' + params.urlencode()})

@login_required
def integrations(request):
    projects = projects_for(request.user)
    leaders = list(projects.filter(workspace__memberships__user=request.user, workspace__memberships__role='leader'))
    heartbeat = WorkerHeartbeat.objects.filter(name='automation').first()
    healthy = bool(heartbeat and timezone.now() - heartbeat.last_seen < timedelta(seconds=90))
    return render(request, 'integrations.html', {'projects': leaders, 'worker_healthy': healthy,
        'heartbeat': heartbeat})

@login_required
def deliveries(request):
    projects = projects_for(request.user).filter(workspace__memberships__user=request.user, workspace__memberships__role='leader')
    selected = request.GET.get('project')
    project = get_object_or_404(projects, pk=selected) if selected else None
    items = Delivery.objects.filter(project__in=projects).select_related('project').order_by('-created_at', '-pk')
    if project:
        items = items.filter(project=project)
    page = Paginator(items, 30).get_page(request.GET.get('page'))
    def page_url(number):
        params = request.GET.copy()
        params['page'] = number
        return '?' + params.urlencode()
    return render(request, 'deliveries.html', {'projects': projects, 'project': project, 'deliveries': page.object_list, 'page': page,
        'previous_url': page_url(page.previous_page_number()) if page.has_previous() else '',
        'next_url': page_url(page.next_page_number()) if page.has_next() else ''})

@login_required
@require_POST
def retry_delivery(request, pk):
    delivery = get_object_or_404(Delivery, pk=pk, project__in=projects_for(request.user))
    leader_required(request.user, delivery.project.workspace)
    if delivery.state in ('failed', 'attention'):
        delivery.state = 'pending'
        delivery.result = ''
        delivery.save(update_fields=['state', 'result'])
        messages.success(request, 'Queued for another processing attempt.')
    return redirect(reverse('deliveries') + '?project=' + str(delivery.project_id))

@csrf_exempt
@require_POST
def webhook(request, pk):
    project = get_object_or_404(Project, pk=pk)
    try: body = request.body
    except RequestDataTooBig: return JsonResponse({'error': 'Payload too large'}, status=413)
    expected = 'sha256=' + hmac.new(project.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get('X-Hub-Signature-256', '')):
        return JsonResponse({'error': 'Invalid signature'}, status=403)
    delivery_id = request.headers.get('X-GitHub-Delivery', '')
    event = request.headers.get('X-GitHub-Event', '')
    if not delivery_id or len(delivery_id) > 100 or not event or len(event) > 80:
        return JsonResponse({'error': 'Invalid delivery headers'}, status=400)
    try: payload = json.loads(body)
    except (ValueError, UnicodeDecodeError): return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if not isinstance(payload, dict): return JsonResponse({'error': 'Expected an object'}, status=400)
    repository = payload.get('repository')
    if not isinstance(repository, dict) or not isinstance(repository.get('full_name'), str) or repository['full_name'].lower() != project.repository:
        return JsonResponse({'error': 'Repository mismatch'}, status=400)
    delivery, created = Delivery.objects.get_or_create(project=project, delivery_id=delivery_id,
        defaults={'event': event, 'payload': payload})
    return JsonResponse({'accepted': True, 'duplicate': not created}, status=202 if created else 200)
