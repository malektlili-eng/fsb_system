"""
apps/accounts/views.py (V2)
"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout, get_user_model
from django.contrib import messages
from core.permissions import role_required, min_role_required

logger = logging.getLogger(__name__)
User = get_user_model()


def home(request):
    if request.user.is_authenticated:
        return redirect('administration:dashboard')
    return redirect('accounts:login')


@min_role_required('scolarite')
def profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name).strip()
        user.last_name  = request.POST.get('last_name', user.last_name).strip()
        user.email      = request.POST.get('email', user.email).strip()
        user.telephone  = request.POST.get('telephone', user.telephone).strip()

        # Changement de mot de passe optionnel
        new_pwd = request.POST.get('new_password', '').strip()
        if new_pwd:
            if len(new_pwd) < 8:
                messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
                return redirect('accounts:profile')
            user.set_password(new_pwd)
            messages.info(request, "Mot de passe modifié. Veuillez vous reconnecter.")

        user.save()
        messages.success(request, "Profil mis à jour.")
        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'user': request.user})


@role_required('super_admin')
def gestion_agents(request):
    """Gestion des comptes utilisateurs — super_admin uniquement."""
    agents = User.objects.all().order_by('role', 'last_name', 'first_name')

    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'create':
            try:
                username = request.POST['username'].strip()
                password = request.POST['password']

                if User.objects.filter(username=username).exists():
                    messages.error(request, f"Le nom d'utilisateur «{username}» est déjà pris.")
                elif len(password) < 8:
                    messages.error(request, "Le mot de passe doit contenir au moins 8 caractères.")
                else:
                    u = User.objects.create_user(
                        username=username,
                        password=password,
                        first_name=request.POST.get('first_name', '').strip(),
                        last_name=request.POST.get('last_name', '').strip(),
                        email=request.POST.get('email', '').strip(),
                        role=request.POST.get('role', 'scolarite'),
                    )
                    u.telephone  = request.POST.get('telephone', '').strip()
                    u.departement = request.POST.get('departement', '').strip()
                    u.save()
                    messages.success(request, f"Agent {u.get_full_name()} créé.")
            except Exception as e:
                messages.error(request, f"Erreur : {e}")

        elif action == 'toggle':
            try:
                agent = User.objects.get(pk=request.POST['agent_id'])
                if agent == request.user:
                    messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
                else:
                    agent.is_active = not agent.is_active
                    agent.save(update_fields=['is_active'])
                    etat = "activé" if agent.is_active else "désactivé"
                    messages.success(request, f"Compte de {agent.get_full_name()} {etat}.")
            except User.DoesNotExist:
                messages.error(request, "Utilisateur introuvable.")

        return redirect('accounts:gestion_agents')

    return render(request, 'accounts/gestion_agents.html', {
        'agents': agents,
        'roles': User.ROLE_CHOICES,
    })


def logout_view(request):
    auth_logout(request)
    return redirect('accounts:login')
