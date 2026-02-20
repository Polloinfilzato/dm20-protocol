/**
 * Party Mode Player UI — WebSocket Client & DOM Controller
 *
 * D&D Beyond-style tabbed interface with WebSocket connection,
 * auto-reconnect, message routing, action submission, and
 * character data rendering across 4 tabs.
 *
 * No external dependencies. Vanilla JavaScript only.
 */

(function () {
    'use strict';

    // ===== Configuration =====
    var config = window.PARTY_CONFIG || {};
    var TOKEN = config.token || '';
    var PLAYER_ID = config.playerId || '';
    var PLAYER_NAME = config.playerName || PLAYER_ID;
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
    let activeTab = 'game';
    let cachedCharacterData = null;

    // Audio playback state
    let audioContext = null;
    let audioChunkBuffers = {};  // keyed by stream id (sequence tracking)
    let audioPlaybackQueue = [];
    let isPlayingAudio = false;

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
        headerName: $('.header__name'),
        headerSubtitle: $('.header__subtitle'),
        hpFill: $('.hp-bar__fill'),
        hpText: $('.hp-bar__text'),
        acValue: $('#stat-ac'),
        levelValue: $('#stat-level'),
        speedValue: $('#stat-speed'),
        initValue: $('#stat-init'),
        initBadge: $('#stat-init-badge'),
        conditions: $('.header__conditions'),
        combatBanner: $('.combat-banner'),
        combatInfo: $('.combat-banner__info'),
        initiativeList: $('.initiative-list'),
        abilityGrid: $('.ability-grid'),
        savingThrowsList: $('.saving-throws-list'),
        skillsList: $('.skills-list'),
        featuresList: $('.features-list'),
        proficienciesSummary: $('.proficiencies-summary'),
        spellcastingHeader: $('.spellcasting-header'),
        spellSlots: $('.spell-slots'),
        spellsKnownList: $('.spells-known-list'),
        equipmentSlots: $('.equipment-slots'),
        inventoryList: $('.inventory-list'),
        currencyDisplay: $('.currency-display'),
        currencySection: $('#currency-section'),
    };


    // ===== Tab Switching =====

    function switchTab(tabName) {
        if (tabName === activeTab) return;
        activeTab = tabName;

        // Update content visibility
        $$('.tab-content').forEach(function (el) {
            el.classList.toggle('tab-content--active', el.dataset.tab === tabName);
        });

        // Update tab bar buttons
        $$('.tab-bar__btn').forEach(function (btn) {
            btn.classList.toggle('tab-bar__btn--active', btn.dataset.tab === tabName);
        });
    }


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
                addSystemMessage('Connected as ' + PLAYER_NAME);
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
                updateCharacterTabs(msg.data);
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

            case 'audio':
                handleAudioChunk(msg);
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
        dom.narrativeFeed.scrollTop = dom.narrativeFeed.scrollHeight;
    }

    function addNarrativeMessage(msg) {
        // Server sends narrative text in "narrative" field, not "content"
        var text = msg.content || msg.narrative || '';
        var el = createMessageEl('message--narrative', 'Narrator', text, msg.timestamp);
        appendToFeed(el);
    }

    function addPrivateMessage(msg) {
        var sender = msg.from || 'DM';
        // Server sends private text in "private" field
        var text = msg.content || msg.private || msg.narrative || '';
        var el = createMessageEl('message--private', sender + ' (private)', text, msg.timestamp);

        if (dom.privateMessages) {
            dom.privateMessages.appendChild(el);
            privateMessageCount++;
            if (dom.privateCount) {
                dom.privateCount.textContent = privateMessageCount;
            }
        }

        var feedEl = createMessageEl('message--private', sender + ' (private)', text, msg.timestamp);
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
                    setActionStatus('Action sent', 'queued');

                    // Clear "sent" status after 3s if not yet processing
                    setTimeout(function () {
                        if (pendingActionId === data.action_id) {
                            setActionStatus('', '');
                        }
                    }, 3000);

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
        fetch(API_BASE + '/character/' + encodeURIComponent(PLAYER_ID) + '?token=' + TOKEN)
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (data) {
                if (data) {
                    cachedCharacterData = data;
                    updateCharacterBar(data);
                    updateCharacterTabs(data);
                }
            })
            .catch(function (err) {
                console.error('Failed to fetch character:', err);
            });
    }

    function updateCharacterBar(data) {
        if (!data) return;

        // Name (with player name if available)
        if (dom.headerName && data.name) {
            var displayName = data.name;
            if (data.player_name) {
                displayName += ' (Player: ' + data.player_name + ')';
            }
            dom.headerName.textContent = displayName;
        }

        // Subtitle (race + class)
        if (dom.headerSubtitle) {
            var parts = [];
            if (data.race) {
                var raceName = typeof data.race === 'string' ? data.race : data.race.name || '';
                if (data.race.subrace) raceName = data.race.subrace + ' ' + raceName;
                parts.push(raceName);
            }
            if (data.classes) {
                parts.push(data.classes.map(function (c) { return c.name + ' ' + c.level; }).join('/'));
            }
            dom.headerSubtitle.textContent = parts.join(' \u2022 ');
        }

        // HP
        var hp = data.hit_points_current || data.hit_points || data.hp || 0;
        var maxHp = data.hit_points_max || data.max_hit_points || data.max_hp || hp || 1;
        var hpPercent = Math.max(0, Math.min(100, (hp / maxHp) * 100));

        if (dom.hpFill) {
            dom.hpFill.style.width = hpPercent + '%';
            if (hpPercent > 50) {
                dom.hpFill.style.background = 'linear-gradient(90deg, #28a745, #34d058)';
            } else if (hpPercent > 25) {
                dom.hpFill.style.background = 'linear-gradient(90deg, #e6a817, #f0c040)';
            } else {
                dom.hpFill.style.background = 'linear-gradient(90deg, #c53131, #e74c3c)';
            }
        }
        if (dom.hpText) {
            dom.hpText.textContent = hp + '/' + maxHp;
        }

        // AC
        if (dom.acValue && data.armor_class !== undefined) {
            dom.acValue.textContent = data.armor_class;
        }

        // Level
        if (dom.levelValue && data.classes) {
            var totalLevel = data.classes.reduce(function (sum, c) { return sum + (c.level || 0); }, 0);
            dom.levelValue.textContent = totalLevel;
        }

        // Speed
        if (dom.speedValue && data.speed !== undefined) {
            dom.speedValue.textContent = data.speed;
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

    // D&D 5e skill -> ability mapping
    var SKILL_ABILITY_MAP = {
        'Acrobatics': 'dexterity', 'Animal Handling': 'wisdom',
        'Arcana': 'intelligence', 'Athletics': 'strength',
        'Deception': 'charisma', 'History': 'intelligence',
        'Insight': 'wisdom', 'Intimidation': 'charisma',
        'Investigation': 'intelligence', 'Medicine': 'wisdom',
        'Nature': 'intelligence', 'Perception': 'wisdom',
        'Performance': 'charisma', 'Persuasion': 'charisma',
        'Religion': 'intelligence', 'Sleight of Hand': 'dexterity',
        'Stealth': 'dexterity', 'Survival': 'wisdom',
    };

    var ABILITY_SHORT = {
        'strength': 'STR', 'dexterity': 'DEX', 'constitution': 'CON',
        'intelligence': 'INT', 'wisdom': 'WIS', 'charisma': 'CHA',
    };

    function getAbilityMod(abilities, abilityName) {
        var ab = (abilities || {})[abilityName];
        var score = ab ? (ab.score || 10) : 10;
        return Math.floor((score - 10) / 2);
    }

    function formatMod(mod) {
        return mod >= 0 ? '+' + mod : '' + mod;
    }

    function updateCharacterTabs(data) {
        if (!data) return;
        cachedCharacterData = data;
        updateAbilityScores(data);
        updateSavingThrows(data);
        updateSkills(data);
        updateFeatures(data);
        updateProficiencies(data);
        updateSpellcasting(data);
        updateSpellSlots(data);
        updateSpellsKnown(data);
        updateEquipment(data);
        updateInventory(data);
        updateCurrency(data);
    }

    function updateAbilityScores(data) {
        if (!dom.abilityGrid || !data.abilities) return;
        dom.abilityGrid.innerHTML = '';

        var abilityDefs = [
            { short: 'STR', full: 'strength' },
            { short: 'DEX', full: 'dexterity' },
            { short: 'CON', full: 'constitution' },
            { short: 'INT', full: 'intelligence' },
            { short: 'WIS', full: 'wisdom' },
            { short: 'CHA', full: 'charisma' },
        ];

        abilityDefs.forEach(function (a) {
            var score = (data.abilities[a.full] || {}).score || 10;
            var mod = Math.floor((score - 10) / 2);

            var el = document.createElement('div');
            el.className = 'ability-score';
            el.innerHTML =
                '<div class="ability-score__name">' + a.short + '</div>' +
                '<div class="ability-score__value">' + score + '</div>' +
                '<div class="ability-score__modifier">' + formatMod(mod) + '</div>';
            dom.abilityGrid.appendChild(el);
        });
    }

    function updateSavingThrows(data) {
        if (!dom.savingThrowsList || !data.abilities) return;
        dom.savingThrowsList.innerHTML = '';

        var profBonus = data.proficiency_bonus || 2;
        var saveProfList = (data.saving_throw_proficiencies || []).map(function (s) { return s.toLowerCase(); });

        var abilityNames = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'];
        abilityNames.forEach(function (ability) {
            var mod = getAbilityMod(data.abilities, ability);
            var isProficient = saveProfList.indexOf(ability) !== -1;
            var bonus = mod + (isProficient ? profBonus : 0);

            var el = document.createElement('div');
            el.className = 'save-item' + (isProficient ? ' save-item--proficient' : '');
            el.innerHTML =
                '<span class="save-item__dot"></span>' +
                '<span class="save-item__name">' + ABILITY_SHORT[ability] + '</span>' +
                '<span class="save-item__bonus">' + formatMod(bonus) + '</span>';
            dom.savingThrowsList.appendChild(el);
        });
    }

    function updateSkills(data) {
        if (!dom.skillsList || !data.abilities) return;
        dom.skillsList.innerHTML = '';

        var profBonus = data.proficiency_bonus || 2;
        var profList = (data.skill_proficiencies || []).map(function (s) { return s.toLowerCase(); });

        Object.keys(SKILL_ABILITY_MAP).forEach(function (skillName) {
            var ability = SKILL_ABILITY_MAP[skillName];
            var mod = getAbilityMod(data.abilities, ability);
            var isProficient = profList.indexOf(skillName.toLowerCase()) !== -1;
            var bonus = mod + (isProficient ? profBonus : 0);

            var el = document.createElement('div');
            el.className = 'skill-item' + (isProficient ? ' skill-item--proficient' : '');
            el.innerHTML =
                '<span class="skill-item__dot"></span>' +
                '<span class="skill-item__name">' + skillName + '</span>' +
                '<span class="skill-item__ability">' + ABILITY_SHORT[ability] + '</span>' +
                '<span class="skill-item__bonus">' + formatMod(bonus) + '</span>';
            dom.skillsList.appendChild(el);
        });
    }

    function updateFeatures(data) {
        if (!dom.featuresList) return;
        dom.featuresList.innerHTML = '';

        var features = data.features || [];
        var legacyFeatures = data.features_and_traits || [];

        features.forEach(function (f) {
            var li = document.createElement('li');
            li.className = 'feature-item';
            var html = '<span class="feature-item__name">' + escapeHtml(f.name) + '</span>';
            if (f.source) {
                html += '<span class="feature-item__source">(' + escapeHtml(f.source) + ')</span>';
            }
            if (f.description) {
                html += '<div class="feature-item__desc">' + f.description + '</div>';
            }
            li.innerHTML = html;
            dom.featuresList.appendChild(li);
        });

        legacyFeatures.forEach(function (f) {
            var li = document.createElement('li');
            li.className = 'feature-item';
            li.innerHTML = '<span class="feature-item__name">' + escapeHtml(f) + '</span>';
            dom.featuresList.appendChild(li);
        });

        if (features.length === 0 && legacyFeatures.length === 0) {
            dom.featuresList.innerHTML = '<li class="feature-item" style="color:var(--text-muted)">No features yet</li>';
        }
    }

    function updateProficiencies(data) {
        if (!dom.proficienciesSummary) return;
        dom.proficienciesSummary.innerHTML = '';

        var groups = [
            { label: 'Languages', items: data.languages || [] },
            { label: 'Tools', items: data.tool_proficiencies || [] },
            { label: 'Armor & Weapons', items: data.armor_proficiencies || data.weapon_proficiencies || [] },
        ];

        groups.forEach(function (g) {
            if (g.items.length === 0) return;
            var div = document.createElement('div');
            div.className = 'prof-group';
            div.innerHTML =
                '<div class="prof-group__label">' + g.label + '</div>' +
                '<div class="prof-group__items">' + g.items.map(escapeHtml).join(', ') + '</div>';
            dom.proficienciesSummary.appendChild(div);
        });

        if (dom.proficienciesSummary.children.length === 0) {
            dom.proficienciesSummary.innerHTML = '<div class="prof-group" style="color:var(--text-muted);font-size:0.85rem">No proficiencies recorded</div>';
        }
    }

    function updateSpellcasting(data) {
        if (!dom.spellcastingHeader) return;
        dom.spellcastingHeader.innerHTML = '';

        var ability = data.spellcasting_ability;
        if (!ability && data.classes) {
            // Infer from class
            var spellclasses = { 'wizard': 'intelligence', 'cleric': 'wisdom', 'druid': 'wisdom',
                'bard': 'charisma', 'sorcerer': 'charisma', 'warlock': 'charisma',
                'paladin': 'charisma', 'ranger': 'wisdom', 'artificer': 'intelligence' };
            data.classes.forEach(function (c) {
                if (!ability && spellclasses[c.name.toLowerCase()]) {
                    ability = spellclasses[c.name.toLowerCase()];
                }
            });
        }

        if (!ability) return;

        var profBonus = data.proficiency_bonus || 2;
        var abilityMod = getAbilityMod(data.abilities || {}, ability);
        var spellSaveDC = 8 + profBonus + abilityMod;
        var spellAttack = profBonus + abilityMod;

        var stats = [
            { label: 'Ability', value: (ABILITY_SHORT[ability] || ability).toUpperCase() },
            { label: 'Spell Save DC', value: spellSaveDC },
            { label: 'Spell Attack', value: formatMod(spellAttack) },
        ];

        stats.forEach(function (s) {
            var div = document.createElement('div');
            div.className = 'spellcasting-stat';
            div.innerHTML =
                '<div class="spellcasting-stat__label">' + s.label + '</div>' +
                '<div class="spellcasting-stat__value">' + s.value + '</div>';
            dom.spellcastingHeader.appendChild(div);
        });
    }

    function updateSpellSlots(data) {
        if (!dom.spellSlots) return;
        dom.spellSlots.innerHTML = '';

        if (!data.spell_slots) {
            dom.spellSlots.innerHTML = '<span style="font-size:0.82rem;color:var(--text-muted)">No spell slots</span>';
            return;
        }

        var slotLevels = Object.keys(data.spell_slots).sort(function (a, b) { return a - b; });
        if (slotLevels.length === 0) {
            dom.spellSlots.innerHTML = '<span style="font-size:0.82rem;color:var(--text-muted)">No spell slots</span>';
            return;
        }

        slotLevels.forEach(function (level) {
            var max = data.spell_slots[level];
            var used = (data.spell_slots_used || {})[level] || 0;
            if (max <= 0) return;

            var container = document.createElement('div');
            container.className = 'spell-slot-level';

            var label = document.createElement('div');
            label.className = 'spell-slot-level__label';
            label.textContent = level === '0' || level === 0 ? 'Cantrip' : 'Lv ' + level;
            container.appendChild(label);

            var dots = document.createElement('div');
            dots.className = 'spell-slot-level__dots';
            for (var i = 0; i < max; i++) {
                var dot = document.createElement('div');
                dot.className = 'spell-slot-dot' + (i < used ? ' spell-slot-dot--used' : '');
                dots.appendChild(dot);
            }
            container.appendChild(dots);

            dom.spellSlots.appendChild(container);
        });
    }

    function updateSpellsKnown(data) {
        if (!dom.spellsKnownList) return;
        dom.spellsKnownList.innerHTML = '';

        var spells = data.spells_known || [];
        if (spells.length === 0) {
            dom.spellsKnownList.innerHTML = '<div class="no-spells-message">No spells known</div>';
            return;
        }

        // Group by level
        var grouped = {};
        spells.forEach(function (spell) {
            var level = spell.level !== undefined ? spell.level : 0;
            if (!grouped[level]) grouped[level] = [];
            grouped[level].push(spell);
        });

        var levels = Object.keys(grouped).sort(function (a, b) { return a - b; });
        levels.forEach(function (level) {
            var group = document.createElement('div');
            group.className = 'spell-level-group';

            var header = document.createElement('div');
            header.className = 'spell-level-group__header';
            header.textContent = level === '0' || level === 0 ? 'Cantrips' : 'Level ' + level;
            group.appendChild(header);

            grouped[level].forEach(function (spell) {
                var entry = document.createElement('div');
                entry.className = 'spell-entry';

                var nameHtml = '<span class="spell-entry__name">' + escapeHtml(spell.name || spell) + '</span>';
                if (spell.school) {
                    nameHtml += ' <span class="spell-entry__school">' + escapeHtml(spell.school) + '</span>';
                }

                var tagsHtml = '<div class="spell-entry__tags">';
                if (spell.concentration) {
                    tagsHtml += '<span class="spell-entry__tag spell-entry__tag--concentration">C</span>';
                }
                if (spell.ritual) {
                    tagsHtml += '<span class="spell-entry__tag spell-entry__tag--ritual">R</span>';
                }
                tagsHtml += '</div>';

                entry.innerHTML = '<div>' + nameHtml + '</div>' + tagsHtml;
                group.appendChild(entry);
            });

            dom.spellsKnownList.appendChild(group);
        });
    }

    function updateEquipment(data) {
        if (!dom.equipmentSlots) return;
        dom.equipmentSlots.innerHTML = '';

        var equipment = data.equipment || {};
        var slotDefs = [
            { key: 'main_hand', label: 'Main Hand' },
            { key: 'off_hand', label: 'Off Hand' },
            { key: 'armor', label: 'Armor' },
            { key: 'shield', label: 'Shield' },
        ];

        var hasAny = false;
        slotDefs.forEach(function (slot) {
            var item = equipment[slot.key];
            if (item || hasAny) hasAny = true;

            var el = document.createElement('div');
            el.className = 'equip-slot';

            var itemName = '';
            if (item) {
                itemName = typeof item === 'string' ? item : item.name || item;
            }

            el.innerHTML =
                '<span class="equip-slot__label">' + slot.label + '</span>' +
                '<span class="equip-slot__item' + (!itemName ? ' equip-slot__item--empty' : '') + '">' +
                (itemName ? escapeHtml(itemName) : 'Empty') + '</span>';
            dom.equipmentSlots.appendChild(el);
        });

        // Also show any equipped items from inventory
        var inv = data.inventory || [];
        inv.forEach(function (item) {
            if (typeof item === 'object' && item.equipped) {
                var alreadyShown = slotDefs.some(function (s) {
                    var eq = equipment[s.key];
                    return eq && (eq === item.name || (eq && eq.name === item.name));
                });
                if (!alreadyShown) {
                    var el = document.createElement('div');
                    el.className = 'equip-slot';
                    el.innerHTML =
                        '<span class="equip-slot__label">Equipped</span>' +
                        '<span class="equip-slot__item">' + escapeHtml(item.name) + '</span>';
                    dom.equipmentSlots.appendChild(el);
                }
            }
        });
    }

    function updateInventory(data) {
        if (!dom.inventoryList) return;
        dom.inventoryList.innerHTML = '';

        var inventory = data.inventory || [];
        if (inventory.length === 0) {
            dom.inventoryList.innerHTML = '<li class="inventory-item" style="color:var(--text-muted);justify-content:center">Inventory is empty</li>';
            return;
        }

        inventory.forEach(function (item) {
            var li = document.createElement('li');
            li.className = 'inventory-item';

            var name = typeof item === 'string' ? item : item.name || item;
            var isObj = typeof item === 'object';
            var qty = (isObj && item.quantity > 1) ? 'x' + item.quantity : '';
            var weight = (isObj && item.weight) ? item.weight + ' lb' : '';
            var type = (isObj && item.type) ? item.type : '';
            var equipped = (isObj && item.equipped);

            var html = '<div class="inventory-item__info">';
            html += '<span class="inventory-item__name">' + escapeHtml(name) + '</span>';
            if (type) html += '<span class="inventory-item__type">' + escapeHtml(type) + '</span>';
            html += '</div>';
            html += '<div class="inventory-item__meta">';
            if (equipped) html += '<span class="inventory-item__equipped-badge">E</span>';
            if (qty) html += '<span class="inventory-item__qty">' + qty + '</span>';
            if (weight) html += '<span class="inventory-item__weight">' + weight + '</span>';
            html += '</div>';

            li.innerHTML = html;
            dom.inventoryList.appendChild(li);
        });
    }

    function updateCurrency(data) {
        if (!dom.currencyDisplay || !dom.currencySection) return;

        var currency = data.currency || data.gold || null;
        if (!currency) {
            dom.currencySection.style.display = 'none';
            return;
        }

        dom.currencySection.style.display = 'block';
        dom.currencyDisplay.innerHTML = '';

        if (typeof currency === 'number') {
            // Simple gold amount
            var el = document.createElement('div');
            el.className = 'currency-item';
            el.innerHTML = '<span class="currency-item__value">' + currency + '</span><span class="currency-item__label">GP</span>';
            dom.currencyDisplay.appendChild(el);
        } else if (typeof currency === 'object') {
            var coins = [
                { key: 'pp', label: 'PP' },
                { key: 'gp', label: 'GP' },
                { key: 'ep', label: 'EP' },
                { key: 'sp', label: 'SP' },
                { key: 'cp', label: 'CP' },
            ];
            coins.forEach(function (c) {
                var val = currency[c.key];
                if (val !== undefined && val > 0) {
                    var el = document.createElement('div');
                    el.className = 'currency-item';
                    el.innerHTML = '<span class="currency-item__value">' + val + '</span><span class="currency-item__label">' + c.label + '</span>';
                    dom.currencyDisplay.appendChild(el);
                }
            });
        }
    }


    // ===== Combat State =====

    let combatActive = false;
    let simultaneousTimer = null;

    function updateCombatState(data) {
        if (!data || !dom.combatBanner) return;

        if (!data.active) {
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

        dom.combatBanner.classList.remove('combat-banner--simultaneous');
        dom.combatBanner.classList.toggle('combat-banner--your-turn', isMyTurn);
        dom.combatBanner.classList.toggle('combat-banner--waiting', !isMyTurn);
        clearSimultaneousTimer();

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

        if (isMyTurn) {
            enableActionInput();
        } else {
            disableActionInput();
        }

        renderInitiativeList(data.initiative, data.current_turn);
    }

    function renderSimultaneousMode(data) {
        dom.combatBanner.classList.remove('combat-banner--your-turn');
        dom.combatBanner.classList.remove('combat-banner--waiting');
        dom.combatBanner.classList.add('combat-banner--simultaneous');

        if (dom.combatInfo) {
            var prompt = data.prompt || 'Everyone act simultaneously!';
            var submitted = data.submitted || [];
            var waiting = data.waiting_for || [];
            var iHaveSubmitted = submitted.indexOf(PLAYER_ID) !== -1 || submitted.indexOf(PLAYER_NAME) !== -1;

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

        if (data.timeout_seconds && !simultaneousTimer) {
            startSimultaneousTimer(data.timeout_seconds);
        }

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
            if (id === PLAYER_ID || id === PLAYER_NAME || name === PLAYER_NAME) el.classList.add('initiative-entry--self');

            var hp = entry.hp || 0;
            var maxHp = entry.max_hp || 1;
            var hpPercent = Math.max(0, Math.min(100, (hp / maxHp) * 100));
            var hpColor = hpPercent > 50 ? '#28a745' : (hpPercent > 25 ? '#e6a817' : '#c53131');

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
        if (domMic && sttSupported && !sttDenied) domMic.disabled = false;
        var overlay = document.querySelector('.turn-gate-overlay');
        if (overlay) overlay.classList.remove('turn-gate-overlay--active');
    }

    function disableActionInput() {
        if (dom.actionInput) {
            dom.actionInput.disabled = true;
            dom.actionInput.placeholder = 'Waiting for your turn...';
        }
        if (dom.actionSend) dom.actionSend.disabled = true;
        if (domMic) domMic.disabled = true;
        // Stop STT if listening while input gets disabled
        if (sttListening && sttRecognition) {
            sttRecognition.abort();
            stopSTT();
        }
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


    // ===== Audio Playback =====

    function getAudioContext() {
        if (!audioContext) {
            try {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
            } catch (e) {
                console.warn('Web Audio API not available:', e);
                return null;
            }
        }
        // Resume if suspended (browser autoplay policy)
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }
        return audioContext;
    }

    function base64ToArrayBuffer(base64) {
        var binary = atob(base64);
        var bytes = new Uint8Array(binary.length);
        for (var i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes.buffer;
    }

    function handleAudioChunk(msg) {
        var seq = msg.sequence || 0;
        var total = msg.total_chunks || 1;

        // Use a simple stream ID based on the first chunk's arrival
        // (all chunks of a single synthesis share the same total_chunks + duration_ms)
        var streamId = 'stream_' + total + '_' + (msg.duration_ms || 0);

        if (!audioChunkBuffers[streamId]) {
            audioChunkBuffers[streamId] = {
                chunks: new Array(total),
                received: 0,
                total: total,
                format: msg.format || 'wav',
                sampleRate: msg.sample_rate || 24000,
            };
        }

        var stream = audioChunkBuffers[streamId];
        stream.chunks[seq] = base64ToArrayBuffer(msg.data);
        stream.received++;

        // All chunks received — reassemble and queue for playback
        if (stream.received >= stream.total) {
            var totalSize = 0;
            stream.chunks.forEach(function (buf) {
                if (buf) totalSize += buf.byteLength;
            });

            var combined = new Uint8Array(totalSize);
            var offset = 0;
            stream.chunks.forEach(function (buf) {
                if (buf) {
                    combined.set(new Uint8Array(buf), offset);
                    offset += buf.byteLength;
                }
            });

            delete audioChunkBuffers[streamId];
            queueAudioPlayback(combined.buffer);
        }
    }

    function queueAudioPlayback(arrayBuffer) {
        audioPlaybackQueue.push(arrayBuffer);
        if (!isPlayingAudio) {
            playNextAudio();
        }
    }

    function playNextAudio() {
        if (audioPlaybackQueue.length === 0) {
            isPlayingAudio = false;
            return;
        }

        isPlayingAudio = true;
        var ctx = getAudioContext();
        if (!ctx) {
            audioPlaybackQueue.length = 0;
            isPlayingAudio = false;
            return;
        }

        var buffer = audioPlaybackQueue.shift();

        ctx.decodeAudioData(buffer, function (audioBuffer) {
            var source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            source.onended = function () {
                playNextAudio();
            };
            source.start(0);
        }, function (err) {
            console.warn('Failed to decode audio:', err);
            playNextAudio();
        });
    }


    // ===== Speech-to-Text (STT) =====

    var sttSupported = false;
    var sttRecognition = null;
    var sttListening = false;
    var sttDenied = false;

    var domMic = null;
    var domMicDot = null;
    var domTranscriptPreview = null;

    function initSTT() {
        var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            // STT not available — mic button stays hidden, text input works normally
            return;
        }

        sttSupported = true;
        sttRecognition = new SpeechRecognition();
        sttRecognition.continuous = false;
        sttRecognition.interimResults = true;
        sttRecognition.maxAlternatives = 1;

        // Default to browser locale, fallback to en-US
        var lang = navigator.language || 'en-US';
        sttRecognition.lang = lang;

        // Cache DOM references
        domMic = $('.action-bar__mic');
        domMicDot = $('.mic-listening-dot');
        domTranscriptPreview = $('.voice-transcript-preview');

        // Show mic button
        if (domMic) {
            domMic.hidden = false;
            domMic.addEventListener('click', toggleSTT);
        }

        sttRecognition.onresult = function (event) {
            var transcript = '';
            var isFinal = false;

            for (var i = event.resultIndex; i < event.results.length; i++) {
                transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    isFinal = true;
                }
            }

            if (isFinal) {
                // Send the transcribed text as an action
                hideTranscriptPreview();
                submitVoiceAction(transcript.trim());
                stopSTT();
            } else {
                // Show interim transcript
                showTranscriptPreview(transcript);
            }
        };

        sttRecognition.onerror = function (event) {
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                sttDenied = true;
                if (domMic) {
                    domMic.classList.add('action-bar__mic--denied');
                    domMic.title = 'Microphone access denied';
                }
            } else if (event.error === 'no-speech') {
                // Timeout — no speech detected, just stop quietly
            } else {
                console.warn('STT error:', event.error);
            }
            stopSTT();
        };

        sttRecognition.onend = function () {
            // Recognition ended (timeout, manual stop, or after final result)
            if (sttListening) {
                stopSTT();
            }
        };
    }

    function toggleSTT() {
        if (sttDenied || !sttSupported) return;

        if (sttListening) {
            sttRecognition.abort();
            stopSTT();
        } else {
            startSTT();
        }
    }

    function startSTT() {
        if (!sttRecognition || sttListening || sttDenied) return;

        // Ensure AudioContext is resumed (needed for some browsers)
        getAudioContext();

        try {
            sttRecognition.start();
            sttListening = true;

            if (domMic) {
                domMic.classList.add('action-bar__mic--listening');
            }
            if (domMicDot) {
                domMicDot.hidden = false;
            }
            showTranscriptPreview('Listening...');
        } catch (e) {
            console.warn('Failed to start STT:', e);
            stopSTT();
        }
    }

    function stopSTT() {
        sttListening = false;

        if (domMic) {
            domMic.classList.remove('action-bar__mic--listening');
        }
        if (domMicDot) {
            domMicDot.hidden = true;
        }
        hideTranscriptPreview();
    }

    function submitVoiceAction(text) {
        if (!text) return;

        // Use the same action submission path, but add voice source
        if (dom.actionInput) {
            dom.actionInput.disabled = true;
        }
        if (dom.actionSend) dom.actionSend.disabled = true;
        setActionStatus('Sending...', 'queued');

        fetch(API_BASE + '/action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + TOKEN,
            },
            body: JSON.stringify({ action: text, source: 'voice' }),
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                if (data.success) {
                    pendingActionId = data.action_id;
                    setActionStatus('Action sent', 'queued');
                    setTimeout(function () {
                        if (pendingActionId === data.action_id) {
                            setActionStatus('', '');
                        }
                    }, 3000);

                    var el = createMessageEl('message--action', PLAYER_NAME, text, new Date().toISOString());
                    appendToFeed(el);
                } else {
                    setActionStatus('Error: ' + (data.error || 'Unknown'), 'error');
                }
            })
            .catch(function (err) {
                setActionStatus('Failed to send action', 'error');
                console.error('Voice action submission error:', err);
            })
            .finally(function () {
                if (dom.actionInput) dom.actionInput.disabled = false;
                if (dom.actionSend) dom.actionSend.disabled = false;
            });
    }

    function showTranscriptPreview(text) {
        if (!domTranscriptPreview) return;
        domTranscriptPreview.textContent = text;
        domTranscriptPreview.hidden = false;
        domTranscriptPreview.classList.toggle('voice-transcript-preview--active', text !== 'Listening...');
    }

    function hideTranscriptPreview() {
        if (!domTranscriptPreview) return;
        domTranscriptPreview.hidden = true;
        domTranscriptPreview.textContent = '';
        domTranscriptPreview.classList.remove('voice-transcript-preview--active');
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

        // Tab bar buttons
        $$('.tab-bar__btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                switchTab(btn.dataset.tab);
            });
        });

        // Private messages toggle
        if (dom.privateToggle) {
            dom.privateToggle.addEventListener('click', togglePrivateMessages);
        }
    }


    // ===== Init =====

    function init() {
        initEventListeners();
        initSTT();
        connect();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
