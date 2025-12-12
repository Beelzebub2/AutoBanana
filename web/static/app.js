const state = {
    latestLogTs: 0,
    offline: false,
    formEditing: false,
    formFocusDepth: 0,
    manualEdit: false,
    serviceState: "idle",
    gameIds: [],
    gameMeta: {},
    gameSearch: {
        term: "",
        results: [],
        activeIndex: -1,
        controller: null,
    },
    themeMap: {
        fire: { start: "#2b1328", end: "#ff6b4a", accent: "#ffcf6f", accent2: "#ff8a5c" },
        ice: { start: "#0d1b2a", end: "#6ea8ff", accent: "#9ee8ff", accent2: "#7dd3fc" },
        pinkneon: { start: "#1b1035", end: "#ff64d6", accent: "#ffb1f5", accent2: "#8ef1ff" },
        rainbow: { start: "#1a1a40", end: "#6a11cb", accent: "#fcb045", accent2: "#00c9ff" },
        matrix: { start: "#041b0a", end: "#0f5132", accent: "#4ade80", accent2: "#22c55e" },
        sunset: { start: "#24160b", end: "#ff7e5f", accent: "#f6d365", accent2: "#ff9a62" },
        default: { start: "#1c2541", end: "#0b132b", accent: "#f6c344", accent2: "#3dd6d0" },
    },
};

const GAME_HINT_DEFAULT = "Press Enter or Space to add an ID. Paste Steam store links or steam:// URLs.";
const GAME_SEARCH_MIN = 2;

const el = (id) => document.getElementById(id);
const consoleEl = () => el("console");
const page = document.body.dataset.page || "dashboard";
const updateFormEditingFlag = () => {
    state.formEditing = state.manualEdit || state.formFocusDepth > 0;
};
const suggestionsEl = () => el("game-token-suggestions");
let gameSearchDebounce;

function normalizeAppId(value) {
    const digits = String(value ?? "").match(/(\d{3,})/);
    return digits ? digits[1] || digits[0] : null;
}

function resultAppId(result) {
    if (!result) return null;
    return normalizeAppId(result.app_id ?? result.appId ?? result.appid ?? result.id ?? result.appID);
}

function updateAccountProgress(progress, accounts, canSwitch) {
    const fill = el("account-progress-fill");
    const title = el("account-progress-title");
    const pill = el("account-progress-pill");
    const count = el("account-progress-count");
    const active = el("account-progress-account");
    const list = el("account-pill-wrap");
    if (!fill || !title || !pill || !count || !active || !list) return;

    const total = progress?.total ?? accounts.length ?? 0;
    const completed = Math.min(progress?.completed ?? 0, total || 0);
    const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((completed / total) * 100))) : 0;

    fill.style.width = `${pct}%`;
    title.textContent = progress?.message || (total ? "All accounts idle" : "No Steam profiles detected");
    pill.textContent = progress?.phase ? progress.phase.replace(/_/g, " ").toUpperCase() : (total ? "IDLE" : "NO ACCOUNTS");
    pill.classList.toggle("alert", progress?.phase === "failed");
    pill.classList.toggle("active", Boolean(progress));

    if (total) {
        count.textContent = `${completed}/${total} completed`;
    } else {
        count.textContent = "0 accounts configured";
    }

    if (progress?.current_account) {
        active.textContent = `Active: ${progress.current_account}`;
    } else if (accounts.length) {
        active.textContent = `Next: ${accounts[0]}`;
    } else {
        active.textContent = "--";
    }

    list.innerHTML = "";
    if (accounts.length) {
        accounts.forEach((name) => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "account-pill";
            if (progress?.current_account && progress.current_account.toLowerCase() === name.toLowerCase()) {
                chip.classList.add("active");
            }

            if (canSwitch) {
                chip.classList.add("clickable");
                chip.addEventListener("click", () => requestAccountSwitch(name));
            } else {
                chip.disabled = true;
                chip.classList.add("disabled");
            }

            chip.textContent = name;
            list.appendChild(chip);
        });
    } else {
        const chip = document.createElement("span");
        chip.className = "account-pill muted";
        chip.textContent = "No remembered accounts";
        list.appendChild(chip);
    }
}

function normalizeGameList(list) {
    if (!Array.isArray(list)) return [];
    const seen = new Set();
    const result = [];
    list.forEach((entry) => {
        const value = String(entry || "").trim();
        if (value && !seen.has(value)) {
            seen.add(value);
            result.push(value);
        }
    });
    return result;
}

function setGameIds(ids) {
    state.gameIds = normalizeGameList(ids);
    renderGameTokens();
    fetchGameMeta(state.gameIds);
}

function renderGameTokens() {
    const listEl = el("game-token-list");
    const input = el("game-token-input");
    if (!listEl) return;
    listEl.innerHTML = "";

    if (!state.gameIds.length) {
        const placeholder = document.createElement("span");
        placeholder.className = "token-chip muted";
        placeholder.textContent = "No games added yet";
        listEl.appendChild(placeholder);
    } else {
        state.gameIds.forEach((id) => {
            const chip = document.createElement("span");
            chip.className = "token-chip";
            const meta = state.gameMeta[id];
            if (meta) {
                chip.classList.add("preview");
                const imageSrc = meta.capsule_image || meta.header_image || meta.icon;
                if (imageSrc) {
                    const img = document.createElement("img");
                    img.src = imageSrc;
                    img.alt = meta.name || `App ${id}`;
                    chip.appendChild(img);
                }

                const copy = document.createElement("span");
                copy.className = "token-copy";
                const title = document.createElement("span");
                title.className = "token-title";
                title.textContent = meta.name || `App ${id}`;
                const idLabel = document.createElement("span");
                idLabel.className = "token-id";
                idLabel.textContent = `App ID ${id}`;
                copy.appendChild(title);
                copy.appendChild(idLabel);
                chip.appendChild(copy);
            } else {
                chip.textContent = id;
            }
            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.setAttribute("aria-label", `Remove ${id}`);
            removeBtn.innerHTML = "&times;";
            removeBtn.addEventListener("click", () => removeGameId(id));
            chip.appendChild(removeBtn);
            listEl.appendChild(chip);
        });
    }

    if (input) {
        input.placeholder = state.gameIds.length ? "Add another ID or link or search by Name" : "Enter app ID or Steam store link";
    }
}

async function fetchGameMeta(ids) {
    const unique = normalizeGameList(ids || []);
    const toFetch = unique.filter((id) => id && !state.gameMeta[id]);
    if (!toFetch.length) return;
    try {
        const res = await fetch(`/api/steam/apps?ids=${toFetch.join(",")}`);
        if (!res.ok) throw new Error("Failed to fetch Steam metadata");
        const data = await res.json();
        if (data.apps) {
            state.gameMeta = { ...state.gameMeta, ...data.apps };
            renderGameTokens();
        }
    } catch (err) {
        console.warn("Steam metadata lookup failed", err);
    }
}

function setGameTokenHint(message = GAME_HINT_DEFAULT, tone = "muted") {
    const hint = el("game-token-hint");
    if (!hint) return;
    hint.textContent = message;
    hint.dataset.tone = tone;
}

function extractGameId(raw) {
    const value = String(raw ?? "").trim();
    if (!value) return null;

    let match = value.match(/app\/(\d+)/i);
    if (match) return match[1];

    match = value.match(/steam:\/\/(?:rungameid|run|install)\/(\d+)/i);
    if (match) return match[1];

    match = value.match(/run(?:gameid)?\/(\d+)/i);
    if (match) return match[1];

    match = value.match(/(\d{3,})/);
    if (match) return match[1];

    return null;
}

function addGameIdFromValue(raw) {
    const id = extractGameId(raw);
    if (!id) {
        setGameTokenHint("Could not find an app ID in that entry.", "error");
        return false;
    }
    if (state.gameIds.includes(id)) {
        setGameTokenHint("App ID already added.", "warning");
        return false;
    }
    state.gameIds.push(id);
    renderGameTokens();
    fetchGameMeta([id]);
    setGameTokenHint();
    markManualEdit();
    return true;
}

function removeGameId(id) {
    state.gameIds = state.gameIds.filter((entry) => entry !== id);
    renderGameTokens();
    setGameTokenHint();
    markManualEdit();
}

function commitGameTokenInput() {
    const input = el("game-token-input");
    if (!input) return;
    const value = input.value.trim();
    if (!value) {
        setGameTokenHint();
        return;
    }
    if (addGameIdFromValue(value)) {
        input.value = "";
        hideGameSearchResults();
    }
}

function handleGameTokenPaste(event) {
    event.preventDefault();
    const text = event.clipboardData?.getData("text") || "";
    text
        .split(/[\s,]+/)
        .map((chunk) => chunk.trim())
        .filter(Boolean)
        .forEach((chunk) => addGameIdFromValue(chunk));
    const input = el("game-token-input");
    if (input) input.value = "";
    hideGameSearchResults();
}

function suggestionsAreVisible() {
    const box = suggestionsEl();
    return Boolean(box && !box.classList.contains("hidden") && state.gameSearch.results.length);
}

function hideGameSearchResults() {
    const box = suggestionsEl();
    if (state.gameSearch.controller) {
        state.gameSearch.controller.abort();
        state.gameSearch.controller = null;
    }
    state.gameSearch.results = [];
    state.gameSearch.activeIndex = -1;
    if (box) {
        box.classList.add("hidden");
        box.classList.remove("loading");
        box.innerHTML = "";
    }
}

function updateSearchActiveIndex(index) {
    state.gameSearch.activeIndex = index;
    renderGameSearchResults();
}

function cycleSearchActive(step) {
    const results = state.gameSearch.results || [];
    if (!results.length) return;
    const total = results.length;
    const current = state.gameSearch.activeIndex >= 0 ? state.gameSearch.activeIndex : 0;
    const next = (current + step + total) % total;
    state.gameSearch.activeIndex = next;
    renderGameSearchResults();
}

function renderGameSearchResults() {
    const box = suggestionsEl();
    if (!box) return;
    const results = state.gameSearch.results || [];
    box.innerHTML = "";

    if (!results.length) {
        const empty = document.createElement("div");
        empty.className = "token-suggestion";
        const meta = document.createElement("div");
        meta.className = "suggestion-meta";
        meta.textContent = state.gameSearch.term.length >= GAME_SEARCH_MIN ? "No matches found" : "Keep typing to search";
        empty.appendChild(meta);
        empty.style.cursor = "default";
        box.appendChild(empty);
        box.classList.remove("hidden");
        return;
    }

    results.forEach((result, index) => {
        const appId = resultAppId(result);
        const row = document.createElement("div");
        row.className = "token-suggestion";
        if (index === state.gameSearch.activeIndex) {
            row.classList.add("active");
        }
        const img = document.createElement("img");
        img.src = result.image || "";
        img.alt = result.name || `App ${result.app_id}`;
        row.appendChild(img);

        const copy = document.createElement("div");
        copy.className = "suggestion-copy";
        const title = document.createElement("div");
        title.className = "suggestion-title";
        title.textContent = result.name || (appId ? `App ${appId}` : "Steam app");
        const meta = document.createElement("div");
        meta.className = "suggestion-meta";
        const priceLabel = result.price ? `${result.price} · ` : "";
        meta.textContent = appId ? `${priceLabel}App ID ${appId}` : priceLabel || "";
        copy.appendChild(title);
        copy.appendChild(meta);
        row.appendChild(copy);

        const add = document.createElement("span");
        add.className = "add-label";
        add.textContent = "Add";
        row.appendChild(add);

        row.addEventListener("mouseenter", () => updateSearchActiveIndex(index));
        row.addEventListener("mousedown", (event) => {
            event.preventDefault();
            selectGameSuggestion(index);
        });
        row.addEventListener("click", (event) => {
            event.preventDefault();
            selectGameSuggestion(index);
        });
        box.appendChild(row);
    });

    box.classList.remove("hidden");
}

async function performGameSearch(term) {
    const query = (term || "").trim();
    const box = suggestionsEl();
    if (!box) return;
    if (query.length < GAME_SEARCH_MIN) {
        hideGameSearchResults();
        return;
    }

    if (state.gameSearch.controller) {
        state.gameSearch.controller.abort();
    }

    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    if (controller) {
        state.gameSearch.controller = controller;
    }

    box.classList.remove("hidden");
    box.classList.add("loading");

    try {
        const res = await fetch(`/api/steam/search?q=${encodeURIComponent(query)}`, {
            signal: controller?.signal,
        });
        if (!res.ok) throw new Error("Steam search failed");
        const data = await res.json();
        const rawResults = Array.isArray(data.results) ? data.results : [];
        state.gameSearch.results = rawResults.slice(0, 10).map((item) => {
            const appId = resultAppId(item);
            if (appId) {
                return { ...item, app_id: appId };
            }
            return item;
        });
        state.gameSearch.activeIndex = state.gameSearch.results.length ? 0 : -1;
        renderGameSearchResults();
    } catch (err) {
        if (err.name === "AbortError") return;
        const message = document.createElement("div");
        message.className = "token-suggestion";
        const meta = document.createElement("div");
        meta.className = "suggestion-meta";
        meta.textContent = "Steam search is unavailable right now";
        message.appendChild(meta);
        box.innerHTML = "";
        box.appendChild(message);
        box.classList.remove("hidden");
    } finally {
        box.classList.remove("loading");
        state.gameSearch.controller = null;
    }
}

function handleGameSearchInput(value) {
    const term = (value || "").trim();
    state.gameSearch.term = term;
    if (gameSearchDebounce) clearTimeout(gameSearchDebounce);
    if (term.length < GAME_SEARCH_MIN) {
        hideGameSearchResults();
        return;
    }
    gameSearchDebounce = setTimeout(() => performGameSearch(term), 220);
}

function selectGameSuggestion(index) {
    const result = state.gameSearch.results[index];
    if (!result) return;
    const appId = resultAppId(result);
    if (!appId) {
        setGameTokenHint("Steam entry is missing an app ID.", "error");
        return;
    }
    const added = addGameIdFromValue(appId);
    if (added) {
        if (result.name || result.image) {
            state.gameMeta[appId] = {
                app_id: appId,
                name: result.name,
                capsule_image: result.image,
                header_image: result.image,
            };
            renderGameTokens();
        }
        fetchGameMeta([appId]);
        const input = el("game-token-input");
        if (input) {
            input.value = "";
            input.focus();
        }
        hideGameSearchResults();
    }
}

function handleGameTokenKeydown(event) {
    const visible = suggestionsAreVisible();
    if (event.key === "ArrowDown" && visible) {
        event.preventDefault();
        cycleSearchActive(1);
        return;
    }
    if (event.key === "ArrowUp" && visible) {
        event.preventDefault();
        cycleSearchActive(-1);
        return;
    }
    if (event.key === "Escape" && visible) {
        event.preventDefault();
        hideGameSearchResults();
        return;
    }
    if (event.key === "Enter") {
        event.preventDefault();
        if (visible && state.gameSearch.activeIndex >= 0) {
            selectGameSuggestion(state.gameSearch.activeIndex);
        } else {
            commitGameTokenInput();
        }
        return;
    }
    if ([" ", ","].includes(event.key) && !visible) {
        event.preventDefault();
        commitGameTokenInput();
    }
}

function setupGameTokenInput() {
    const input = el("game-token-input");
    if (!input) return;
    setGameTokenHint();
    renderGameTokens();
    input.addEventListener("focus", beginFormFocus);
    input.addEventListener("blur", () => {
        commitGameTokenInput();
        endFormFocus();
    });
    input.addEventListener("keydown", handleGameTokenKeydown);
    input.addEventListener("input", (event) => handleGameSearchInput(event.target.value));
    input.addEventListener("paste", handleGameTokenPaste);

    const suggestionBox = suggestionsEl();
    if (suggestionBox) {
        suggestionBox.addEventListener("mousedown", (event) => event.preventDefault());
    }

    input.addEventListener("blur", () => {
        setTimeout(() => hideGameSearchResults(), 120);
    });

    document.addEventListener("click", (event) => {
        const wrap = el("game-token-input-wrap");
        if (!wrap) return;
        if (!wrap.contains(event.target)) {
            hideGameSearchResults();
        }
    });
}

function calculateSwitchStepPct(progress) {
    if (!progress) return null;
    const total = Number(progress.step_total);
    const step = Number(progress.step);
    if (!Number.isFinite(total) || total <= 0) {
        return null;
    }
    const safeStep = Math.min(Math.max(Number.isFinite(step) ? step : 0, 0), total);
    return Math.min(100, Math.max(0, (safeStep / total) * 100));
}

function updateSwitchStepBanner(progress) {
    const banner = el("switch-step-banner");
    const title = el("switch-step-title");
    const count = el("switch-step-count");
    const detail = el("switch-step-detail");
    const fill = el("switch-step-fill");
    if (!banner || !title || !count || !detail || !fill) {
        return;
    }

    if (!progress) {
        banner.classList.add("hidden");
        fill.style.width = "0%";
        count.textContent = "";
        return;
    }

    banner.classList.remove("hidden");
    const pct = calculateSwitchStepPct(progress);
    const phase = (progress.phase || "").toUpperCase();
    const detailText = progress.detail || progress.message || "Working...";
    detail.textContent = detailText;
    title.textContent = progress.message || "Switching Steam accounts";

    if (pct === null) {
        if (phase === "COMPLETE" || phase === "LAUNCHING") {
            fill.style.width = "100%";
        } else {
            fill.style.width = "0%";
        }
        count.textContent = phase || "";
    } else {
        const total = Math.max(1, Number(progress.step_total) || 1);
        const step = Math.min(total, Math.max(0, Number(progress.step) || 0));
        fill.style.width = `${pct}%`;
        count.textContent = `Step ${step}/${total}`;
    }
}

function beginFormFocus() {
    state.formFocusDepth += 1;
    updateFormEditingFlag();
}

function endFormFocus() {
    state.formFocusDepth = Math.max(0, state.formFocusDepth - 1);
    updateFormEditingFlag();
}

function markManualEdit() {
    state.manualEdit = true;
    updateFormEditingFlag();
}

function clearManualEdit() {
    state.manualEdit = false;
    updateFormEditingFlag();
}

function setBanner(visible, message) {
    const banner = el("conn-banner");
    if (!banner) return;
    if (message) banner.textContent = message;
    banner.classList.toggle("hidden", !visible);
}

function setTheme(name) {
    const theme = state.themeMap[name] || state.themeMap.default;
    const root = document.documentElement;
    root.style.setProperty("--bg-start", theme.start);
    root.style.setProperty("--bg-end", theme.end);
    root.style.setProperty("--accent", theme.accent);
    root.style.setProperty("--accent-2", theme.accent2);
    document.body.dataset.theme = name;
}

function fmtTime(iso) {
    if (!iso) return "--";
    const dt = new Date(iso);
    return dt.toLocaleString();
}

function relative(iso) {
    if (!iso) return "";
    const target = new Date(iso).getTime();
    const diff = target - Date.now();
    const absSeconds = Math.max(0, Math.round(Math.abs(diff) / 1000));
    if (absSeconds === 0) return diff >= 0 ? "now" : "just now";
    const formatted = formatDurationVerbose(absSeconds);
    return diff > 0 ? `in ${formatted}` : `${formatted} ago`;
}

function formatDurationHMS(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const pad = (value) => String(value).padStart(2, "0");
    return `${pad(hours)}:${pad(minutes)}:${pad(secs)}`;
}

function formatDurationVerbose(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0 || hours > 0) parts.push(`${minutes}m`);
    parts.push(`${secs}s`);
    return parts.join(" ");
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) throw new Error("status not ok");
        const data = await res.json();
        state.offline = false;
        setBanner(false);
        const cfg = data.config || {};
        if (page === "settings" && state.formEditing) {
            return;
        }

        const statusPill = el("status-pill");
        const heroState = el("hero-state");
        const rawState = data.state || (data.running ? "running" : "idle");
        state.serviceState = rawState;
        const stateLabel = rawState
            .replace(/_/g, " ")
            .replace(/^(.)/, (m) => m.toUpperCase());
        if (heroState) heroState.textContent = stateLabel;
        if (statusPill) {
            const pillLabel = data.state ? data.state.toUpperCase() : (data.running ? "RUNNING" : "IDLE");
            statusPill.textContent = pillLabel;
            statusPill.classList.toggle("active", data.state === "running");
            statusPill.classList.toggle("alert", data.state === "stopped");
        }

        const setText = (id, value, fallback = "--") => {
            const elRef = el(id);
            if (elRef) {
                elRef.textContent = value ?? fallback;
            }
        };

        setText("kpi-next-run", fmtTime(data.next_run_at));
        setText("kpi-next-hint", relative(data.next_run_at) || "waiting");
        setText("kpi-last-run", fmtTime(data.last_run_at));
        setText("kpi-last-hint", relative(data.last_run_at) || "--");
        setText("kpi-accounts", data.accounts_count ?? 0, "0");
        setText("kpi-games", (cfg.games || []).length ?? 0, "0");
        setText("kpi-batch", cfg.batch_size ?? 0, "0");
        setText("kpi-runs", data.game_open_count ?? 0, "0");

        if (page === "dashboard") {
            updateAccountProgress(data.switch_progress, data.accounts || [], rawState === "waiting");
            updateSwitchStepBanner(data.switch_progress);
        }

        const themeName = cfg.theme || "default";
        if (page === "settings") {
            if (el("run-interval")) el("run-interval").value = Math.round((cfg.run_interval_seconds || 0) / 60) || "";
            if (el("wait-seconds")) el("wait-seconds").value = cfg.time_to_wait || "";
            if (el("batch-size-input")) el("batch-size-input").value = cfg.batch_size || "";

            document.querySelectorAll("#theme-chips .chip").forEach((chip) => {
                chip.classList.toggle("active", chip.dataset.theme === themeName);
            });

            const startup = document.querySelector("#startup-switch");
            const switchAccounts = document.querySelector("#switch-accounts-switch");
            if (startup) startup.classList.toggle("active", Boolean(cfg.run_on_startup));
            if (switchAccounts) switchAccounts.classList.toggle("active", Boolean(cfg.switch_steam_accounts));
            setGameIds(cfg.games || []);
            setGameTokenHint();
            setTheme(themeName);
        } else {
            setTheme(themeName);
        }

        // Progress bar on dashboard
        if (page === "dashboard") {
            const fill = el("progress-fill");
            const label = el("progress-label");
            if (fill && label) {
                const interval = data.interval_seconds || 0;
                const next = data.next_run_at ? new Date(data.next_run_at).getTime() : null;
                let pct = 0;
                let text = "Idle";

                fill.classList.remove("loading-anim", "waiting-anim");

                if (data.state === "stopped") {
                    pct = 0;
                    text = "Stopped by user";
                    fill.classList.remove("loading-anim");
                } else {
                    const wp = data.wait_progress;
                    if (wp && wp.total > 0) {
                        // Active waiting action (e.g., waiting before closing games)
                        const total = Number(wp.total) || 0;
                        const elapsed = Number(wp.elapsed) || 0;
                        const remaining = typeof wp.remaining === "number" ? Math.max(0, wp.remaining) : Math.max(0, total - elapsed);
                        const denom = total || (elapsed + remaining) || 1;
                        pct = Math.min(100, Math.max(0, ((denom - remaining) / denom) * 100));
                        text = `${wp.label} (${formatDurationHMS(remaining)} remaining)`;
                        fill.classList.add("waiting-anim");
                    } else if (data.state === "running") {
                        pct = 100;
                        text = "Running current cycle";
                        fill.classList.add("loading-anim");
                    } else if (next && interval > 0) {
                        const now = Date.now();
                        const remaining = Math.max(0, next - now);
                        pct = Math.min(100, Math.max(0, ((interval * 1000 - remaining) / (interval * 1000)) * 100));
                        text = `Next in ${relative(data.next_run_at) || "soon"}`;
                        fill.classList.remove("loading-anim");
                    }
                }

                fill.style.width = `${pct}%`;
                label.textContent = text;
            }
        }
    } catch (err) {
        state.offline = true;
        setBanner(true, "Backend is not reachable. Waiting to reconnect...");
        console.warn("status error", err);
    }
}

async function fetchLogs() {
    if (state.offline) return;
    try {
        const res = await fetch(`/api/logs?since=${state.latestLogTs}`);
        if (!res.ok) return;
        const data = await res.json();
        const events = data.events || [];
        if (events.length) {
            state.latestLogTs = data.latest || state.latestLogTs;
            events.forEach(appendLog);
        }
    } catch (err) {
        console.warn("log error", err);
    }
}

function appendLog(event) {
    const wrapper = document.createElement("div");
    wrapper.className = `console-line ${event.level}`;
    const ts = new Date(event.timestamp * 1000).toLocaleTimeString();
    wrapper.innerHTML = `<span class="ts">${ts}</span><span class="lvl">${event.level}</span><span class="msg">${event.message}</span>`;
    const c = consoleEl();
    if (!c) return;
    const shouldStick = c.scrollTop + c.clientHeight >= c.scrollHeight - 40;
    c.appendChild(wrapper);
    while (c.childNodes.length > 300) c.removeChild(c.firstChild);
    if (shouldStick) c.scrollTop = c.scrollHeight;
}

function clearConsole() {
    const c = consoleEl();
    if (c) {
        c.innerHTML = "";
    }
}

function jumpConsoleToBottom() {
    const c = consoleEl();
    if (!c) return;
    c.scrollTo({ top: c.scrollHeight, behavior: "smooth" });
}

async function requestAccountSwitch(accountName) {
    if (!accountName) return;
    if (state.serviceState !== "waiting") {
        appendLog({ level: "warning", timestamp: Date.now() / 1000, message: "Can only switch accounts while waiting" });
        return;
    }

    try {
        const res = await fetch("/api/switch-account", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account: accountName }),
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) {
            appendLog({ level: "error", timestamp: Date.now() / 1000, message: payload.error || "Manual switch failed" });
            return;
        }
        appendLog({ level: "success", timestamp: Date.now() / 1000, message: payload.message || `Switched to ${accountName}` });
        jumpConsoleToBottom();
        fetchStatus();
    } catch (err) {
        appendLog({ level: "error", timestamp: Date.now() / 1000, message: "Manual switch request failed" });
    }
}

async function saveConfig(e) {
    if (e) e.preventDefault();
    const payload = {
        run_interval_seconds: Number(el("run-interval").value || 0) * 60,
        time_to_wait: Number(el("wait-seconds").value || 0),
        batch_size: Number(el("batch-size-input").value || 0),
        run_on_startup: document.querySelector("#startup-switch")?.classList.contains("active") || false,
        switch_steam_accounts: document.querySelector("#switch-accounts-switch")?.classList.contains("active") || false,
        theme: document.querySelector("#theme-chips .chip.active")?.dataset.theme || "default",
        games: state.gameIds,
    };

    try {
        const res = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("Failed to save config");
        const data = await res.json();
        appendLog({ level: "info", timestamp: Date.now() / 1000, message: "Configuration saved" });
        el("save-status").textContent = "Saved";
        setTimeout(() => (el("save-status").textContent = ""), 2000);
        clearManualEdit();
        const cfg = data.config || {};
        setTheme(cfg.theme || "default");
        if (page === "settings") {
            setGameIds(cfg.games || []);
        }
    } catch (err) {
        appendLog({ level: "error", timestamp: Date.now() / 1000, message: err.message });
    }
}

async function runNow() {
    try {
        await fetch("/api/run", { method: "POST" });
        appendLog({ level: "info", timestamp: Date.now() / 1000, message: "Run queued" });
        jumpConsoleToBottom();
    } catch (err) {
        appendLog({ level: "error", timestamp: Date.now() / 1000, message: "Could not queue run" });
    }
}

async function stopScheduler() {
    try {
        await fetch("/api/stop", { method: "POST" });
        appendLog({ level: "warning", timestamp: Date.now() / 1000, message: "Scheduler stopped by user" });
        showNotification("Scheduler stopped", "All running games have been closed.");
        // Immediately update progress bar
        const fill = el("progress-fill");
        const label = el("progress-label");
        const statusPill = el("status-pill");
        if (fill) {
            fill.style.width = "0%";
            fill.classList.remove("loading-anim");
        }
        if (label) label.textContent = "Stopped by user";
        if (statusPill) statusPill.textContent = "STOPPED";
    } catch (err) {
        appendLog({ level: "error", timestamp: Date.now() / 1000, message: "Could not stop scheduler" });
    }
}

function showNotification(title, body) {
    // In-page toast notification
    let toast = document.getElementById("toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast";
        toast.className = "toast";
        document.body.appendChild(toast);
    }
    toast.innerHTML = `<strong>${title}</strong><span>${body}</span>`;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 4000);
}

function init() {
    document.body.dataset.theme = document.body.dataset.theme || "default";
    setTheme(document.body.dataset.theme);

    if (page === "settings" && el("config-form")) {
        el("config-form").addEventListener("submit", saveConfig);
        document.querySelectorAll("#theme-chips .chip").forEach((chip) => {
            chip.addEventListener("click", () => {
                document.querySelectorAll("#theme-chips .chip").forEach((c) => c.classList.remove("active"));
                chip.classList.add("active");
                setTheme(chip.dataset.theme);
                markManualEdit();
            });
        });
        document.querySelectorAll(".switch").forEach((sw) => {
            sw.addEventListener("click", () => {
                sw.classList.toggle("active");
                markManualEdit();
            });
        });

        ["run-interval", "wait-seconds", "batch-size-input"].forEach((id) => {
            const input = el(id);
            if (input) {
                input.addEventListener("focus", beginFormFocus);
                input.addEventListener("blur", endFormFocus);
                ["input", "change"].forEach((evt) => input.addEventListener(evt, markManualEdit));
            }
        });

        setupGameTokenInput();
    }

    if (el("run-now")) el("run-now").addEventListener("click", runNow);
    if (el("stop")) el("stop").addEventListener("click", stopScheduler);
    if (el("console-clear")) el("console-clear").addEventListener("click", clearConsole);
    if (el("console-jump")) el("console-jump").addEventListener("click", jumpConsoleToBottom);

    fetchStatus();
    fetchLogs();
    setInterval(fetchStatus, 500);
    setTimeout(() => setInterval(fetchLogs, 1000), 300);
}

document.addEventListener("DOMContentLoaded", init);
