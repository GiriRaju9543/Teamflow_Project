from django.contrib.auth import views as auth
from django.urls import include, path

urlpatterns = [
    path('login/', auth.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth.LogoutView.as_view(), name='logout'),
    path('', include('flow.urls')),
]
