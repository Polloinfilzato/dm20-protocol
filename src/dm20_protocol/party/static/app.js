/**
 * Party Mode Player UI — WebSocket Client & DOM Controller
 *
 * Handles WebSocket connection with auto-reconnect, message routing,
 * action submission, character data fetching, and UI updates.
 *
 * No external dependencies. Vanilla JavaScript only.
 */

(function () {
    'use strict';

    // ===== Configuration =====
    // Token and player name are injected via window.PARTY_CONFIG in the HTML
    var config = window.PARTY_CONFIG || {};
    var TOKEN = config.token || '';
    var PLAYER_NAME = config.playerName || '';
    var WS_URL = 'ws://' + window.location.host + '/ws?token=' + TOKEN;
    const API_BASE = window.location.origin;

    // Reconnect settings
    const RECONNECT_BASE_MS = 1000;
    const RECONNECT_MAX_MS = 30000;
    const HEARTBEAT_INTERVAL_MS = 30000;

    // ===== State =====
    let ws = null;
    let reconnectAttempt = 0;
    let reconnectTimer = null;
    let heartbeatTimer = null;
    let lastSeenTimestamp = null;
    let isConnected = false;
    let pendingActionId = null;
    let privateMessagesExpanded = false;
    let privateMessageCount = 0;
    let characterSheetOpen = false;

    // ===== DOM References =====
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dom = {
        connectionDot: $('.connection-dot'),
        narrativeFeed: $('.narrative-feed'),
        privateToggle: $('.private-section__toggle'),
        privateMessages: $('.private-section__messages'),
        privateCount: $('.private-section__count'),
        privateArrow: $('.private-section__toggle-arrow'),
        actionInput: $('.action-bar__input'),
        actionSend: $('.action-bar__send'),
        actionStatus: $('.action-bar__status'),
        actionForm: $('.action-bar__form'),
        characterName: $('.character-bar__name'),
        hpFill: $('.hp-bar__fill'),
        hpText: $('.hp-bar__text'),
        acValue: $('#stat-ac'),
        levelValue: $('#stat-level'),
        conditions: $('.character-bar__conditions'),
        combatBanner: $('.combat-banner'),
        combatInfo: $('.combat-banner__info'),
        initiativeList: $('.initiative-list'),
        sheetOverlay: $('.character-sheet-overlay'),
        sheetPanel: $('.character-sheet'),
        sheetClose: $('.character-sheet__close'),
        sheetTitle: $('.character-sheet__title'),
        sheetSubtitle: $('.character-sheet__subtitle'),
        abilityGrid: $('.ability-grid'),
        skillsList: $('.skills-list'),
        inventoryList: $('.inventory-list'),
        spellSlots: $('.spell-slots'),
        featuresList: $('.features-list'),
    };


    // ===== WebSocket Connection =====

    function connect() {
        if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
            return;
        }

        updateConnectionStatus('reconnecting');
        ws = new WebSocket(WS_URL);

        ws.onopen = function () {
            isConnected = true;
            reconnectAttempt = 0;
            updateConnectionStatus('connected');
            startHeartbeat();

            // Request history if reconnecting
            if (lastSeenTimestamp) {
                ws.send(JSON.stringify({
                    type: 'history_request',
                    since: lastSeenTimestamp,
                }));
            }
        };

        ws.onmessage = function (event) {
            try {
                var msg = JSON.parse(event.data);
                handleMessage(msg);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        ws.onclose = function () {
            isConnected = false;
            stopHeartbeat();
            updateConnectionStatus('disconnected');
            scheduleReconnect();
        };

        ws.onerror = function (err) {
            console.error('WebSocket error:', err);
        };
    }

    function scheduleReconnect() {
        if (reconnectTimer) clearTimeout(reconnectTimer);
        var delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt), RECONNECT_MAX_MS);
        reconnectAttempt++;
        updateConnectionStatus('reconnecting');
        reconnectTimer = setTimeout(connect, delay);
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatTimer = setInterval(function () {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'heartbeat' }));
            }
        }, HEARTBEAT_INTERVAL_MS);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    }

    function updateConnectionStatus(status) {
        if (!dom.connectionDot) return;
        dom.connectionDot.className = 'connection-dot';
        if (status === 'connected') {
            dom.connectionDot.classList.add('connection-dot--connected');
        } else if (status === 'reconnecting') {
            dom.connectionDot.classList.add('connection-dot--reconnecting');
        }
    }


    // ===== Message Handler =====

    function handleMessage(msg) {
        if (msg.timestamp) {
            lastSeenTimestamp = msg.timestamp;
        }

        switch (msg.type) {
            case 'connected':
                addSystemMessage('Connected as ' + (msg.player_id || PLAYER_NAME));
                fetchCharacter();
                break;

            case 'narrative':
                addNarrativeMessage(msg);
                break;

            case 'private':
                addPrivateMessage(msg);
                break;

            case 'character_update':
                updateCharacterBar(msg.data);
                break;

            case 'combat_state':
                updateCombatState(msg.data);
                break;

            case 'action_status':
                updateActionStatus(msg.action_id, msg.status, msg.error);
                break;

            case 'system':
                addSystemMessage(msg.content);
                break;

            default:
                console.log('Unknown message type:', msg.type, msg);
        }
    }


    // ===== Message Rendering =====

    function formatTime(timestamp) {
        if (!timestamp) return '';
        try {
            var d = new Date(timestamp);
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return '';
        }
    }

    function createMessageEl(cssClass, sender, content, timestamp) {
        var el = document.createElement('div');
        el.className = 'message ' + cssClass;
        el.innerHTML =
            '<div class="message__header">' +
            '<span class="message__sender">' + escapeHtml(sender) + '</span>' +
            '<span class="message__timestamp">' + formatTime(timestamp) + '</span>' +
            '</div>' +
            '<div class="message__content">' + escapeHtml(content) + '</div>';
        return el;
    }

    function appendToFeed(el) {
        if (!dom.narrativeFeed) return;
        dom.narrativeFeed.appendChild(el);
        // Auto-scroll to bottom
        dom.narrativeFeed.scrollTop = dom.narrativeFeed.scrollHeight;
    }

    function addNarrativeMessage(msg) {
        var el = createMessageEl('message--narrative', 'Narrator', msg.content, msg.timestamp);
        appendToFeed(el);
    }

    function addPrivateMessage(msg) {
        var sender = msg.from || 'DM';
        var el = createMessageEl('message--private', sender + ' (private)', msg.content, msg.timestamp);

        // Add to private section
        if (dom.privateMessages) {
            dom.privateMessages.appendChild(el);
            privateMessageCount++;
            if (dom.privateCount) {
                dom.privateCount.textContent = privateMessageCount;
            }
        }

        // Also add to main feed
        var feedEl = createMessageEl('message--private', sender + ' (private)', msg.content, msg.timestamp);
        appendToFeed(feedEl);
    }

    function addSystemMessage(content) {
        var el = document.createElement('div');
        el.className = 'message message--system';
        el.innerHTML = '<div class="message__content">' + escapeHtml(content) + '</div>';
        appendToFeed(el);
    }

    function addCombatMessage(content, timestamp) {
        var el = createMessageEl('message--combat', 'Combat', content, timestamp);
        appendToFeed(el);
    }

    function escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }


    // ===== Action Submission =====

    function submitAction() {
        var input = dom.actionInput;
        if (!input) return;

        var text = input.value.trim();
        if (!text) return;

        // Disable input while processing
        input.disabled = true;
        if (dom.actionSend) dom.actionSend.disabled = true;
        setActionStatus('Sending...', 'queued');

        fetch(API_BASE + '/action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + TOKEN,
            },
            body: JSON.stringify({ action: text }),
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    pendingActionId = data.action_id;
                    input.value = '';
                    setActionStatus('Action queued', 'queued');

                    // Also show the action in the feed
                    var el = createMessageEl('message--action', PLAYER_NAME, text, new Date().toISOString());
                    appendToFeed(el);
                } else {
                    setActionStatus('Error: ' + (data.error || 'Unknown'), 'error');
                }
            })
            .catch(function (err) {
                setActionStatus('Failed to send action', 'error');
                console.error('Action submission error:', err);
            })
            .finally(function () {
                input.disabled = false;
                if (dom.actionSend) dom.actionSend.disabled = false;
                input.focus();
            });
    }

    function updateActionStatus(actionId, status, errorMsg) {
        if (status === 'rejected') {
            // Turn gating rejection — not tied to a pending action
            setActionStatus(errorMsg || 'Action rejected', 'error');
            setTimeout(function () { setActionStatus('', ''); }, 3000);
            return;
        }

        if (actionId === pendingActionId) {
            if (status === 'processing') {
                setActionStatus('Processing...', 'processing');
            } else if (status === 'resolved') {
                setActionStatus('Done', 'resolved');
                pendingActionId = null;
                // Clear status after a moment
                setTimeout(function () { setActionStatus('', ''); }, 2000);
            }
        }
    }

    function setActionStatus(text, cssStatus) {
        if (!dom.actionStatus) return;
        dom.actionStatus.textContent = text;
        dom.actionStatus.className = 'action-bar__status';
        if (cssStatus) {
            dom.actionStatus.classList.add('action-bar__status--' + cssStatus);
        }
    }


    // ===== Character Data =====

    function fetchCharacter() {
        fetch(API_BASE + '/character/' + encodeURIComponent(PLAYER_NAME) + '?token=' + TOKEN)
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (data) {
                if (data) {
                    updateCharacterBar(data);
                    updateCharacterSheet(data);
                }
            })
            .catch(function (err) {
                console.error('Failed to fetch character:', err);
            });
    }

    function updateCharacterBar(data) {
        if (!data) return;

        // Name
        if (dom.characterName && data.name) {
            dom.characterName.textContent = data.name;
        }

        // HP
        var hp = data.hit_points || data.hp || 0;
        var maxHp = data.max_hit_points || data.max_hp || hp || 1;
        var hpPercent = Math.max(0, Math.min(100, (hp / maxHp) * 100));

        if (dom.hpFill) {
            dom.hpFill.style.width = hpPercent + '%';
            // Color: green > 50%, yellow 25-50%, red < 25%
            if (hpPercent > 50) {
                dom.hpFill.style.background = 'linear-gradient(90deg, #22c55e, #4ade80)';
            } else if (hpPercent > 25) {
                dom.hpFill.style.background = 'linear-gradient(90deg, #eab308, #facc15)';
            } else {
                dom.hpFill.style.background = 'linear-gradient(90deg, #dc2626, #f87171)';
            }
        }
        if (dom.hpText) {
            dom.hpText.textContent = hp + '/' + maxHp;
        }

        // AC
        if (dom.acValue && (data.armor_class !== undefined || data.ac !== undefined)) {
            dom.acValue.textContent = data.armor_class || data.ac;
        }

        // Level
        if (dom.levelValue && data.level !== undefined) {
            dom.levelValue.textContent = data.level;
        }

        // Conditions
        if (dom.conditions) {
            dom.conditions.innerHTML = '';
            var conditions = data.conditions || [];
            conditions.forEach(function (c) {
                var tag = document.createElement('span');
                tag.className = 'condition-tag';
                tag.textContent = typeof c === 'string' ? c : c.name || c;
                dom.conditions.appendChild(tag);
            });
        }
    }

    function updateCharacterSheet(data) {
        if (!data) return;

        // Title
        if (dom.sheetTitle) {
            dom.sheetTitle.textContent = data.name || PLAYER_NAME;
        }
        if (dom.sheetSubtitle) {
            var parts = [];
            if (data.race) parts.push(data.race);
            if (data.class_name || data.classes) {
                parts.push(data.class_name || (data.classes || []).map(function (c) { return c.name; }).join('/'));
            }
            if (data.level) parts.push('Level ' + data.level);
            dom.sheetSubtitle.textContent = parts.join(' | ');
        }

        // Ability Scores
        if (dom.abilityGrid && data.ability_scores) {
            dom.abilityGrid.innerHTML = '';
            var abilities = ['STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'];
            abilities.forEach(function (name) {
                var key = name.toLowerCase();
                var score = data.ability_scores[key] || data.ability_scores[name] || 10;
                var mod = Math.floor((score - 10) / 2);
                var modStr = mod >= 0 ? '+' + mod : '' + mod;

                var el = document.createElement('div');
                el.className = 'ability-score';
                el.innerHTML =
                    '<div class="ability-score__name">' + name + '</div>' +
                    '<div class="ability-score__value">' + score + '</div>' +
                    '<div class="ability-score__modifier">' + modStr + '</div>';
                dom.abilityGrid.appendChild(el);
            });
        }

        // Inventory
        if (dom.inventoryList && data.inventory) {
            dom.inventoryList.innerHTML = '';
            (data.inventory || []).forEach(function (item) {
                var li = document.createElement('li');
                li.className = 'inventory-item';
                var name = typeof item === 'string' ? item : item.name || item;
                var equipped = (typeof item === 'object' && item.equipped) ? '<span class="inventory-item__equipped">E</span>' : '';
                var qty = (typeof item === 'object' && item.quantity > 1) ? '<span class="inventory-item__qty">x' + item.quantity + '</span>' : '';
                li.innerHTML = '<span class="inventory-item__name">' + escapeHtml(name) + '</span>' + equipped + qty;
                dom.inventoryList.appendChild(li);
            });
        }
    }


    // ===== Combat State =====

    let combatActive = false;
    let simultaneousTimer = null;

    function updateCombatState(data) {
        if (!data || !dom.combatBanner) return;

        if (!data.active) {
            // Combat ended
            if (combatActive) {
                addSystemMessage('Combat ended');
            }
            combatActive = false;
            dom.combatBanner.classList.remove('combat-banner--active');
            dom.combatBanner.classList.remove('combat-banner--your-turn');
            dom.combatBanner.classList.remove('combat-banner--waiting');
            dom.combatBanner.classList.remove('combat-banner--simultaneous');
            enableActionInput();
            clearSimultaneousTimer();
            return;
        }

        combatActive = true;
        dom.combatBanner.classList.add('combat-banner--active');

        if (data.mode === 'simultaneous') {
            renderSimultaneousMode(data);
        } else {
            renderTurnBasedMode(data);
        }
    }

    function renderTurnBasedMode(data) {
        var isMyTurn = data.your_turn === true;

        // Banner state
        dom.combatBanner.classList.remove('combat-banner--simultaneous');
        dom.combatBanner.classList.toggle('combat-banner--your-turn', isMyTurn);
        dom.combatBanner.classList.toggle('combat-banner--waiting', !isMyTurn);
        clearSimultaneousTimer();

        // Banner text
        if (dom.combatInfo) {
            var roundText = data.round ? ' &mdash; Round ' + data.round : '';
            if (isMyTurn) {
                dom.combatInfo.innerHTML =
                    '<span class="combat-banner__your-turn-text">YOUR TURN</span>' +
                    roundText;
            } else {
                var current = data.current_turn || 'Unknown';
                dom.combatInfo.innerHTML =
                    'Waiting for <span class="combat-banner__current">' +
                    escapeHtml(current) + '</span>' + roundText;
            }
        }

        // Turn gating
        if (isMyTurn) {
            enableActionInput();
        } else {
            disableActionInput();
        }

        // Initiative list with enhanced entries
        renderInitiativeList(data.initiative, data.current_turn);
    }

    function renderSimultaneousMode(data) {
        dom.combatBanner.classList.remove('combat-banner--your-turn');
        dom.combatBanner.classList.remove('combat-banner--waiting');
        dom.combatBanner.classList.add('combat-banner--simultaneous');

        // Show prompt
        if (dom.combatInfo) {
            var prompt = data.prompt || 'Everyone act simultaneously!';
            var submitted = data.submitted || [];
            var waiting = data.waiting_for || [];
            var iHaveSubmitted = submitted.indexOf(PLAYER_NAME) !== -1;

            dom.combatInfo.innerHTML =
                '<div class="combat-banner__prompt">' + escapeHtml(prompt) + '</div>' +
                '<div class="combat-banner__simul-status">' +
                'Submitted: ' + (submitted.length > 0 ? submitted.map(escapeHtml).join(', ') : 'none') +
                ' &mdash; Waiting: ' + (waiting.length > 0 ? waiting.map(escapeHtml).join(', ') : 'none') +
                '</div>';

            if (iHaveSubmitted) {
                disableActionInput();
            } else {
                enableActionInput();
            }
        }

        // Countdown timer
        if (data.timeout_seconds && !simultaneousTimer) {
            startSimultaneousTimer(data.timeout_seconds);
        }

        // Clear initiative list for simultaneous mode
        if (dom.initiativeList) {
            dom.initiativeList.innerHTML = '';
        }
    }

    function renderInitiativeList(initiative, currentTurn) {
        if (!dom.initiativeList || !initiative) return;
        dom.initiativeList.innerHTML = '';

        initiative.forEach(function (entry) {
            var el = document.createElement('div');
            el.className = 'initiative-entry';

            var id = entry.id || entry.name || entry;
            var name = entry.name || id;

            if (id === currentTurn) el.classList.add('initiative-entry--current');
            if (id === PLAYER_NAME || name === PLAYER_NAME) el.classList.add('initiative-entry--self');

            // Build HP bar
            var hp = entry.hp || 0;
            var maxHp = entry.max_hp || 1;
            var hpPercent = Math.max(0, Math.min(100, (hp / maxHp) * 100));
            var hpColor = hpPercent > 50 ? '#22c55e' : (hpPercent > 25 ? '#eab308' : '#dc2626');

            var conditionsHtml = '';
            if (entry.conditions && entry.conditions.length > 0) {
                conditionsHtml = '<div class="initiative-entry__conditions">' +
                    entry.conditions.map(function (c) {
                        return '<span class="initiative-entry__condition">' + escapeHtml(c) + '</span>';
                    }).join('') + '</div>';
            }

            el.innerHTML =
                '<div class="initiative-entry__header">' +
                '<span class="initiative-entry__name">' + escapeHtml(name) + '</span>' +
                '<span class="initiative-entry__init">' + (entry.initiative || 0) + '</span>' +
                '</div>' +
                '<div class="initiative-entry__stats">' +
                '<div class="initiative-entry__hp-bar">' +
                '<div class="initiative-entry__hp-fill" style="width:' + hpPercent + '%;background:' + hpColor + '"></div>' +
                '</div>' +
                '<span class="initiative-entry__hp-text">' + hp + '/' + maxHp + '</span>' +
                '<span class="initiative-entry__ac">AC ' + (entry.ac || '?') + '</span>' +
                '</div>' +
                conditionsHtml;

            dom.initiativeList.appendChild(el);
        });
    }

    function enableActionInput() {
        if (dom.actionInput) {
            dom.actionInput.disabled = false;
            dom.actionInput.placeholder = 'What do you do?';
        }
        if (dom.actionSend) dom.actionSend.disabled = false;
        // Remove overlay
        var overlay = document.querySelector('.turn-gate-overlay');
        if (overlay) overlay.classList.remove('turn-gate-overlay--active');
    }

    function disableActionInput() {
        if (dom.actionInput) {
            dom.actionInput.disabled = true;
            dom.actionInput.placeholder = 'Waiting for your turn...';
        }
        if (dom.actionSend) dom.actionSend.disabled = true;
        // Show overlay
        var overlay = document.querySelector('.turn-gate-overlay');
        if (overlay) overlay.classList.add('turn-gate-overlay--active');
    }

    function startSimultaneousTimer(seconds) {
        clearSimultaneousTimer();
        var timerEl = document.querySelector('.countdown-timer');
        if (!timerEl) return;

        var remaining = seconds;
        timerEl.style.display = 'block';
        timerEl.textContent = formatCountdown(remaining);

        simultaneousTimer = setInterval(function () {
            remaining--;
            if (remaining <= 0) {
                clearSimultaneousTimer();
                timerEl.textContent = 'Time up!';
            } else {
                timerEl.textContent = formatCountdown(remaining);
            }
        }, 1000);
    }

    function clearSimultaneousTimer() {
        if (simultaneousTimer) {
            clearInterval(simultaneousTimer);
            simultaneousTimer = null;
        }
        var timerEl = document.querySelector('.countdown-timer');
        if (timerEl) timerEl.style.display = 'none';
    }

    function formatCountdown(seconds) {
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }


    // ===== Character Sheet Toggle =====

    function openCharacterSheet() {
        characterSheetOpen = true;
        document.body.classList.add('sheet-open');
        if (dom.sheetOverlay) dom.sheetOverlay.classList.add('character-sheet-overlay--visible');
        if (dom.sheetPanel) dom.sheetPanel.classList.add('character-sheet--open');
    }

    function closeCharacterSheet() {
        characterSheetOpen = false;
        document.body.classList.remove('sheet-open');
        if (dom.sheetOverlay) dom.sheetOverlay.classList.remove('character-sheet-overlay--visible');
        if (dom.sheetPanel) dom.sheetPanel.classList.remove('character-sheet--open');
    }


    // ===== Private Messages Toggle =====

    function togglePrivateMessages() {
        privateMessagesExpanded = !privateMessagesExpanded;
        if (dom.privateMessages) {
            dom.privateMessages.classList.toggle('private-section__messages--expanded', privateMessagesExpanded);
        }
        if (dom.privateArrow) {
            dom.privateArrow.classList.toggle('private-section__toggle-arrow--expanded', privateMessagesExpanded);
        }
    }


    // ===== Event Listeners =====

    function initEventListeners() {
        // Action form
        if (dom.actionForm) {
            dom.actionForm.addEventListener('submit', function (e) {
                e.preventDefault();
                submitAction();
            });
        }

        // Character bar -> open sheet
        var charBar = $('.character-bar');
        if (charBar) {
            charBar.addEventListener('click', openCharacterSheet);
        }

        // Close sheet
        if (dom.sheetClose) {
            dom.sheetClose.addEventListener('click', function (e) {
                e.stopPropagation();
                closeCharacterSheet();
            });
        }

        // Overlay click closes sheet
        if (dom.sheetOverlay) {
            dom.sheetOverlay.addEventListener('click', closeCharacterSheet);
        }

        // Private messages toggle
        if (dom.privateToggle) {
            dom.privateToggle.addEventListener('click', togglePrivateMessages);
        }

        // Keyboard: Enter to submit, Escape to close sheet
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && characterSheetOpen) {
                closeCharacterSheet();
            }
        });
    }


    // ===== Init =====

    function init() {
        initEventListeners();
        connect();
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
