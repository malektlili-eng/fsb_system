"""
apps/examens/urls.py (V2)
"""
from django.urls import path
from . import views

app_name = 'examens'

urlpatterns = [
    path('sessions/', views.liste_sessions, name='sessions'),
    path('sessions/ajouter/', views.ajouter_session, name='ajouter_session'),
    path('planning/', views.planning_examens, name='planning'),
    path('planning/<int:pk>/supprimer/', views.supprimer_planning, name='supprimer_planning'),
    path('resultats/', views.resultats, name='resultats'),
]


# ──────────────────────────────────────────────────────────────────
"""
apps/ai_agent/urls.py (V2)
"""
# Ce fichier est séparé — le coller dans apps/ai_agent/urls.py

AI_AGENT_URLS = """
from django.urls import path
from . import views

app_name = 'ai_agent'

urlpatterns = [
    path('chat/', views.chat_interface, name='chat'),
    path('chat/send/', views.send_message_stream, name='send'),
    path('chat/history/', views.chat_history, name='history'),
    path('chat/clear/', views.clear_all_conversations, name='clear'),
    path('conversation/<int:conv_id>/delete/', views.delete_conversation, name='delete_conversation'),
    path('metrics/', views.agent_metrics, name='metrics'),
]
"""
