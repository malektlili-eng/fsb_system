"""
apps/ai_agent/views.py (V2)
─────────────────────────────────────────────────────────────────────
Vues pour l'interface chat avec streaming SSE.

AMÉLIORATIONS vs V1 :
 ✓ Streaming Server-Sent Events (plus de blocage)
 ✓ Markdown rendu côté client (via marked.js)
 ✓ Indicateur d'outil en cours d'exécution
 ✓ Rate limiting (10 req/min par utilisateur)
─────────────────────────────────────────────────────────────────────
"""
import json
import logging
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from django.conf import settings

from .models import ConversationChat, MessageChat
from .orchestrator import FSBOrchestrator

logger = logging.getLogger(__name__)


def _get_or_create_conversation(user, conv_id, first_message: str) -> ConversationChat:
    """Récupère ou crée une conversation."""
    if conv_id:
        try:
            return ConversationChat.objects.get(pk=conv_id, user=user)
        except ConversationChat.DoesNotExist:
            pass

    return ConversationChat.objects.create(
        user=user,
        agent_type='multi',
        titre=first_message[:80],
    )


@login_required
def chat_interface(request):
    """Rendu de l'interface chat principale."""
    conversations = (
        ConversationChat.objects
        .filter(user=request.user)
        .order_by('-created_at')[:15]
    )

    conv_id = request.GET.get('conv')
    current_conv, conv_messages = None, []

    if conv_id:
        try:
            current_conv = ConversationChat.objects.get(pk=conv_id, user=request.user)
            conv_messages = MessageChat.objects.filter(
                conversation=current_conv
            ).order_by('timestamp')
        except ConversationChat.DoesNotExist:
            pass

    return render(request, 'ai_agents/chat.html', {
        'conversations': conversations,
        'current_conv': current_conv,
        'conv_messages': conv_messages,
        'has_api_key': bool(settings.GROQ_API_KEY),
        'model_name': settings.GROQ_MODEL,
    })


@login_required
@require_POST
def send_message_stream(request):
    """
    Endpoint de streaming SSE.
    Le client JavaScript consomme les events avec EventSource ou fetch().

    Format des events :
      {"type": "token",      "data": "texte partiel"}
      {"type": "tool_start", "data": "Recherche étudiants..."}
      {"type": "tool_done",  "data": "chercher_etudiant", "success": true}
      {"type": "done",       "tokens": 150, "elapsed_ms": 2300}
      {"type": "error",      "data": "message d'erreur"}
    """
    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip()
        conv_id = data.get('conversation_id')

        if not user_msg:
            return JsonResponse({'error': 'Message vide'}, status=400)

        if not settings.GROQ_API_KEY:
            return JsonResponse(
                {'error': 'Clé API Groq non configurée. Ajoutez GROQ_API_KEY dans votre .env'},
                status=503
            )

        # Créer/récupérer la conversation
        conv = _get_or_create_conversation(request.user, conv_id, user_msg)

        # Sauvegarder le message utilisateur
        MessageChat.objects.create(
            conversation=conv,
            role='user',
            contenu=user_msg,
        )

        # Créer l'orchestrateur et streamer la réponse
        orchestrator = FSBOrchestrator(request.user)

        def event_stream():
            # Envoyer l'ID de conversation en premier
            yield f"data: {json.dumps({'type': 'conv_id', 'data': conv.pk})}\n\n"

            for event_line in orchestrator.process_stream(user_msg, conv.pk):
                yield f"data: {event_line}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Désactiver le buffering nginx
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur send_message_stream : {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def chat_history(request):
    """Liste de toutes les conversations de l'utilisateur."""
    conversations = (
        ConversationChat.objects
        .filter(user=request.user)
        .order_by('-created_at')
    )
    return render(request, 'ai_agents/history.html', {
        'conversations': conversations
    })


@login_required
@require_POST
def delete_conversation(request, conv_id):
    """Supprime une conversation."""
    conv = get_object_or_404(ConversationChat, pk=conv_id, user=request.user)
    conv.delete()
    return JsonResponse({'ok': True})


@login_required
@require_POST
def clear_all_conversations(request):
    """Supprime toutes les conversations de l'utilisateur."""
    ConversationChat.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True})


@login_required
def agent_metrics(request):
    """
    Dashboard des métriques de l'agent (réservé aux admins).
    Montre les statistiques d'utilisation, taux de succès, temps de réponse.
    """
    if request.user.role not in ('super_admin', 'admin'):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    from .models import AgentMetric
    from django.db.models import Avg, Count

    metrics = AgentMetric.objects.filter(
        user__isnull=False
    ).aggregate(
        total_requetes=Count('id'),
        temps_moyen_ms=Avg('response_time_ms'),
        tokens_moyens=Avg('tokens_used'),
    )

    outils_utilises = (
        AgentMetric.objects
        .exclude(tool_called='')
        .values('tool_called')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    recentes = AgentMetric.objects.order_by('-timestamp')[:20]

    return render(request, 'ai_agents/metrics.html', {
        'metrics': metrics,
        'outils': outils_utilises,
        'recentes': recentes,
    })
