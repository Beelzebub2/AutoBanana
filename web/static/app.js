const state = {
    latestLogTs: 0,
    offline: false,
    formEditing: false,
    formFocusDepth: 0,
    manualEdit: false,
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

const el = (id) => document.getElementById(id);
const consoleEl = () => el("console");
const page = document.body.dataset.page || "dashboard";
const updateFormEditingFlag = () => {
    state.formEditing = state.manualEdit || state.formFocusDepth > 0;
};

function updateAccountProgress(progress, accounts) {
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
            const chip = document.createElement("span");
            chip.className = "account-pill";
            if (progress?.current_account && progress.current_account.toLowerCase() === name.toLowerCase()) {
                chip.classList.add("active");
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
    const abs = Math.abs(diff);
    const mins = Math.round(abs / 60000);
    if (mins === 0) return diff >= 0 ? "now" : "just now";
    return diff > 0 ? `in ${mins} min` : `${mins} min ago`;
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
        const stateLabel = (data.state || (data.running ? "running" : "idle"))
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
            updateAccountProgress(data.switch_progress, data.accounts || []);
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
                        pct = Math.min(100, Math.max(0, (wp.elapsed / wp.total) * 100));
                        text = `${wp.label} (${wp.elapsed}s / ${wp.total}s)`;
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

async function saveConfig(e) {
    if (e) e.preventDefault();
    const payload = {
        run_interval_seconds: Number(el("run-interval").value || 0) * 60,
        time_to_wait: Number(el("wait-seconds").value || 0),
        batch_size: Number(el("batch-size-input").value || 0),
        run_on_startup: document.querySelector("#startup-switch")?.classList.contains("active") || false,
        switch_steam_accounts: document.querySelector("#switch-accounts-switch")?.classList.contains("active") || false,
        theme: document.querySelector("#theme-chips .chip.active")?.dataset.theme || "default",
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
