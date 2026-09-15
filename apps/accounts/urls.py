"""
apps/accounts/urls.py (V2)
"""
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('',                   views.home,          name='home'),
    path('accounts/login/',
         auth_views.LoginView.as_view(template_name='accounts/login.html'),
         name='login'),
    path('accounts/logout/',   views.logout_view,   name='logout'),
    path('accounts/profile/',  views.profile,       name='profile'),
    path('accounts/agents/',   views.gestion_agents, name='gestion_agents'),
]
