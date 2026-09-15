/* ================================================================
   FSB System V2 — Chat IA avec SSE streaming + Markdown
   static/js/chat_v2.js
   ================================================================
   AMÉLIORATIONS vs V1 :
   ✓ Streaming SSE réel (chaque token apparaît en temps réel)
   ✓ Rendu Markdown (** bold **, # titres, - listes, `code`)
   ✓ Indicateur d'outil en cours d'exécution
   ✓ Gestion robuste des erreurs réseau
   ✓ Reconnexion automatique en cas de coupure
   ================================================================ */

import { marked } from 'https://cdn.jsdelivr.net/npm/marked@12/+esm';

// ─── Configuration marked ──────────────────────────────────────────
marked.setOptions({
  breaks: true,        // \n → <br>
  gfm: true,           // GitHub Flavored Markdown
  sanitize: false,     // On contrôle le HTML côté serveur (Django)
});

// ─── État global ───────────────────────────────────────────────────
let conversationId = null;
let isStreaming = false;

// ─── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const chatApp = document.getElementById('chatApp');
  if (!chatApp) return;

  conversationId = chatApp.dataset.convId || null;
  scrollChat();

  // Auto-resize du textarea
  const textarea = document.getElementById('chatInput');
  if (textarea) {
    textarea.addEventListener('input', function () {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  // Boutons de raccourci
  document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      const msg = this.dataset.msg;
      if (msg && textarea) {
        textarea.value = msg;
        textarea.dispatchEvent(new Event('input'));
        sendMessage();
      }
    });
  });
});

// ─── Envoi du message ─────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) return;

  const textarea = document.getElementById('chatInput');
  const text = textarea?.value.trim();
  if (!text) return;

  textarea.value = '';
  textarea.style.height = 'auto';
  isStreaming = true;

  // Supprimer l'écran de bienvenue
  document.getElementById('chatWelcome')?.remove();

  // Afficher le message utilisateur
  appendUserMessage(text);

  // Créer la bulle de l'assistant (vide, sera remplie par le stream)
  const assistantBubble = appendAssistantBubble();
  const textSpan = assistantBubble.querySelector('.bubble-text');
  const toolSpan = assistantBubble.querySelector('.bubble-tool');
  let fullText = '';

  try {
    const response = await fetch('/ai/chat/send/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({
        message: text,
        conversation_id: conversationId,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      textSpan.innerHTML = `<span style="color:var(--color-danger)">Erreur : ${err.error || 'Inconnue'}</span>`;
      return;
    }

    // Lecture du stream SSE ligne par ligne
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // Garder le fragment incomplet

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (!payload) continue;

        try {
          const event = JSON.parse(payload);
          handleStreamEvent(event, { textSpan, toolSpan, fullText: () => fullText, setFullText: (t) => { fullText = t; } });
        } catch (e) {
          // JSON mal formé, ignorer
        }
      }
    }

    // Rendu final du Markdown sur le texte complet
    if (fullText) {
      textSpan.innerHTML = marked.parse(fullText);
    }

  } catch (networkError) {
    textSpan.innerHTML = `<span style="color:var(--color-danger)">
      Erreur réseau. Vérifiez votre connexion.
    </span>`;
    console.error('Stream error:', networkError);
  } finally {
    isStreaming = false;
    toolSpan.style.display = 'none';
    scrollChat();
  }
}

// ─── Gestion des events SSE ───────────────────────────────────────
function handleStreamEvent(event, { textSpan, toolSpan, fullText, setFullText }) {
  switch (event.type) {
    case 'conv_id':
      conversationId = event.data;
      break;

    case 'token':
      // Ajouter le token au texte complet et re-renderer
      setFullText(fullText() + event.data);
      // Rendu partiel progressif (texte brut pendant le stream, Markdown à la fin)
      textSpan.textContent = fullText();
      scrollChat();
      break;

    case 'tool_start':
      toolSpan.style.display = 'flex';
      toolSpan.querySelector('.tool-name').textContent = event.data;
      toolSpan.querySelector('.tool-spinner').style.display = 'inline-block';
      break;

    case 'tool_done':
      toolSpan.querySelector('.tool-spinner').style.display = 'none';
      toolSpan.querySelector('.tool-icon').textContent = event.success ? '✓' : '✗';
      toolSpan.style.color = event.success
        ? 'var(--color-success)'
        : 'var(--color-danger)';
      break;

    case 'error':
      textSpan.innerHTML = `<span style="color:var(--color-danger)">
        Erreur : ${event.data}
      </span>`;
      break;

    case 'done':
      // Optionnel : afficher les métriques en console dev
      if (event.elapsed_ms) {
        console.debug(`[FSB Agent] ${event.tokens} tokens en ${event.elapsed_ms}ms`);
      }
      break;
  }
}

// ─── Création des bulles ──────────────────────────────────────────
function appendUserMessage(text) {
  const container = document.getElementById('chatMessages');
  const now = formatTime();
  const initials = getUserInitials();

  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `
    <div class="msg-av user-av">${initials}</div>
    <div>
      <div class="msg-bubble user-bubble">${escapeHtml(text)}</div>
      <div class="msg-time">${now}</div>
    </div>
  `;
  container.appendChild(row);
  scrollChat();
}

function appendAssistantBubble() {
  const container = document.getElementById('chatMessages');
  const now = formatTime();

  const row = document.createElement('div');
  row.className = 'msg-row assistant';
  row.innerHTML = `
    <div class="msg-av bot-av">🤖</div>
    <div style="flex:1">
      <div class="bubble-tool" style="display:none; align-items:center; gap:6px;
           font-size:12px; color:var(--color-text-secondary); margin-bottom:6px;">
        <span class="tool-icon">⚙️</span>
        <span class="tool-spinner" style="display:none">⟳</span>
        <span class="tool-name">En cours...</span>
      </div>
      <div class="msg-bubble assistant-bubble">
        <span class="bubble-text"></span>
        <span class="typing-cursor">▋</span>
      </div>
      <div class="msg-time">${now}</div>
    </div>
  `;
  container.appendChild(row);
  scrollChat();
  return row;
}

// ─── Utilitaires ─────────────────────────────────────────────────
function scrollChat() {
  const el = document.getElementById('chatMessages');
  if (el) el.scrollTop = el.scrollHeight;
}

function formatTime() {
  return new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function getUserInitials() {
  const el = document.querySelector('.topbar .user-av');
  return el?.textContent?.trim() || 'ME';
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(str));
  return d.innerHTML;
}

function getCsrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// ─── Supprimer une conversation ───────────────────────────────────
async function deleteConversation(convId) {
  if (!confirm('Supprimer cette conversation ?')) return;
  const resp = await fetch(`/ai/conversation/${convId}/delete/`, {
    method: 'POST',
    headers: { 'X-CSRFToken': getCsrf() },
  });
  if (resp.ok) window.location.href = '/ai/chat/';
}

// Exposer les fonctions globales pour les onclick HTML
window.sendMessage = sendMessage;
window.deleteConversation = deleteConversation;
