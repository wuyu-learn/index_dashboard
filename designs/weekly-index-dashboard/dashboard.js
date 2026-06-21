(() => {
  const data = window.DASHBOARD_DATA || {
    categories: [],
    dates: [],
    latestDate: "",
    firstDate: "",
    indexCount: 0,
  };
  const state = {
    category: data.categories[0]?.name || "",
    mode: "gain",
    scope: "latest",
    trackedCode: null,
  };

  const categoryTabs = document.getElementById("category-tabs");
  const leaderCards = document.getElementById("leader-cards");
  const rankingMatrix = document.getElementById("ranking-matrix");
  const trackedLabel = document.getElementById("tracked-label");

  const formatDate = (value, short = false) => {
    if (!value) return "—";
    return short
      ? `${value.slice(4, 6)}-${value.slice(6, 8)}`
      : `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
  };

  const formatPct = (value) => {
    const pct = Number(value) * 100;
    return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
  };

  const currentCategory = () =>
    data.categories.find((category) => category.name === state.category);

  const rankingKey = () => state.mode === "gain" ? "gainTop" : "lossTop";
  const modeText = () => state.mode === "gain" ? "涨幅" : "跌幅";

  const renderTabs = () => {
    categoryTabs.innerHTML = data.categories.map((category) => `
      <button
        type="button"
        data-category="${category.name}"
        class="${category.name === state.category ? "is-active" : ""}"
      >
        ${category.name}
        <span>${category.count}</span>
      </button>
    `).join("");
  };

  const renderLeaders = () => {
    const category = currentCategory();
    const items = category?.[state.scope]?.[rankingKey()] || [];
    const trackedItem = items.find((item) => item.code === state.trackedCode);
    if (state.trackedCode && !trackedItem) state.trackedCode = null;

    document.getElementById("leader-kicker").textContent =
      state.scope === "latest"
        ? `最新一周 · ${formatDate(data.latestDate)}`
        : `${formatDate(data.firstDate)} → ${formatDate(data.latestDate)}`;
    document.getElementById("leader-title").textContent = `${modeText()}前 3`;

    leaderCards.innerHTML = items.map((item, index) => `
      <button
        type="button"
        class="leader-card ${item.code === state.trackedCode ? "is-selected" : ""}"
        data-code="${item.code}"
        aria-pressed="${item.code === state.trackedCode}"
      >
        <span class="leader-rank">0${index + 1}</span>
        <span class="leader-name">${item.name}</span>
        <strong class="${state.mode}">${formatPct(item.return)}</strong>
        <span class="leader-meta">${item.code}${item.subcategory ? ` · ${item.subcategory}` : ""}</span>
      </button>
    `).join("");

    const hint = document.getElementById("tracking-hint");
    hint.textContent = state.trackedCode
      ? `已追踪「${trackedItem?.name || state.trackedCode}」；再次点击可取消。`
      : "点击上方指数，可在下方各周期榜单中追踪它。";
  };

  const matrixCell = (item) => {
    if (!item) return '<div class="matrix-cell is-empty">—</div>';
    const isTracked = item.code === state.trackedCode;
    return `
      <div class="matrix-cell ${isTracked ? "is-tracked" : ""}" title="${item.name} · ${item.code}">
        <strong>${item.name}</strong>
        <span class="cell-code">${item.code}</span>
        <span class="cell-return ${state.mode}">${formatPct(item.return)}</span>
      </div>
    `;
  };

  const renderMatrix = () => {
    const category = currentCategory();
    const periods = [...(category?.periods || [])].reverse();
    const key = rankingKey();
    const trackedItem = [
      ...(category?.latest?.gainTop || []),
      ...(category?.latest?.lossTop || []),
      ...(category?.interval?.gainTop || []),
      ...(category?.interval?.lossTop || []),
    ].find((item) => item.code === state.trackedCode);

    document.getElementById("matrix-title").textContent = `每周${modeText()}前 5`;
    trackedLabel.hidden = !state.trackedCode;
    trackedLabel.textContent = state.trackedCode
      ? `正在追踪 · ${trackedItem?.name || state.trackedCode}`
      : "";

    const columns = periods.map(() => "minmax(170px, 1fr)").join(" ");
    const header = `
      <div class="matrix-corner">排名</div>
      ${periods.map((period) => `
        <div class="matrix-date">
          <strong>${formatDate(period.date, true)}</strong>
          <span>${period.date === data.latestDate ? "最新" : "周度"}</span>
        </div>
      `).join("")}
    `;
    const rows = Array.from({ length: 5 }, (_, rank) => `
      <div class="matrix-rank"><span>${rank + 1}</span></div>
      ${periods.map((period) => matrixCell(period[key][rank])).join("")}
    `).join("");

    rankingMatrix.style.gridTemplateColumns = `72px ${columns}`;
    rankingMatrix.innerHTML = header + rows;
  };

  const render = () => {
    renderTabs();
    renderLeaders();
    renderMatrix();
    document.querySelectorAll("[data-mode]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.mode === state.mode);
    });
    document.querySelectorAll("[data-scope]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.scope === state.scope);
    });
  };

  const resetTracking = () => {
    state.trackedCode = null;
  };

  categoryTabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.category = button.dataset.category;
    resetTracking();
    render();
  });

  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      resetTracking();
      render();
    });
  });

  document.querySelectorAll("[data-scope]").forEach((button) => {
    button.addEventListener("click", () => {
      state.scope = button.dataset.scope;
      resetTracking();
      render();
    });
  });

  leaderCards.addEventListener("click", (event) => {
    const card = event.target.closest("[data-code]");
    if (!card) return;
    state.trackedCode = state.trackedCode === card.dataset.code ? null : card.dataset.code;
    render();
  });

  document.getElementById("period-count").textContent = `${data.dates.length} 周`;
  document.getElementById("summary-text").textContent =
    `${data.indexCount} 个有效指数 · ${formatDate(data.firstDate)} 至 ${formatDate(data.latestDate)} · 数据生成于 ${
      new Date(data.generatedAt).toLocaleString("zh-CN", { hour12: false })
    }`;
  render();
})();
