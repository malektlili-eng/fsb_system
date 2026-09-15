"""
GUIDE DE DÉMARRAGE RAPIDE — FSB System V2
==========================================

1. PRÉREQUIS
   pip install -r requirements/development.txt

2. CONFIGURATION
   cp .env.example .env
   # Éditer .env : remplir SECRET_KEY et GROQ_API_KEY

3. BASE DE DONNÉES
   python manage.py makemigrations accounts
   python manage.py makemigrations administration
   python manage.py makemigrations pedagogie
   python manage.py makemigrations examens
   python manage.py makemigrations stages
   python manage.py makemigrations ai_agent
   python manage.py migrate

4. DONNÉES DE DÉMONSTRATION
   python manage.py shell -c "
   from django.contrib.auth import get_user_model
   User = get_user_model()
   User.objects.create_superuser('admin', 'admin@fsb.tn', 'admin123', role='super_admin')
   "
   # Puis lancer l'init_data si disponible :
   python init_data.py

5. LANCER LE SERVEUR
   python manage.py runserver
   # → http://localhost:8000
   # Login : admin / admin123

6. API REST
   # → http://localhost:8000/api/schema/swagger-ui/

7. TESTS
   python manage.py test tests/ -v 2
   coverage run manage.py test tests/ && coverage report

VARIABLE D'ENVIRONNEMENT DJANGO_SETTINGS_MODULE
   # Développement (défaut) :
   export DJANGO_SETTINGS_MODULE=config.settings.development
   # Production :
   export DJANGO_SETTINGS_MODULE=config.settings.production

AVEC DOCKER
   docker-compose up -d
   docker-compose exec web python manage.py migrate
   docker-compose exec web python manage.py createsuperuser
"""
