# Procfile — commande de démarrage pour PaaS (Render, Railway, Heroku…)
# La phase `release` est autonome : migrations, données de démonstration
# et index vectoriel. Une démo qui s'ouvre sur une base vide n'est pas
# une démo. `init_data` est idempotent, donc rejouable à chaque release.
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
release: python manage.py migrate --no-input && python manage.py init_data --quiet && python manage.py build_rag_index
