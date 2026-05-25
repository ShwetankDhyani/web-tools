document.addEventListener("DOMContentLoaded", () => {
  loadUserInfo();
  loadProducts();
  const urlInput = document.getElementById("productUrl");
  if (urlInput) {
    urlInput.addEventListener("input", updateCurrencyHint);
    urlInput.addEventListener("change", updateCurrencyHint);
    urlInput.addEventListener("paste", (e) => {
      setTimeout(() => {
        const cleaned = extractUrlFromPaste(urlInput.value);
        if (cleaned && cleaned !== urlInput.value) {
          urlInput.value = cleaned;
          updateCurrencyHint();
        }
      }, 0);
    });
  }
});

function extractUrlFromPaste(text) {
  const t = (text || "").trim().replace(/[\u200b-\u200d\ufeff\u00a0]/g, "");
  if (!t) return "";
  if (/^https?:\/\//i.test(t)) return t.split(/\s/)[0].replace(/[.,;:!?)\"']+$/, "");
  const m = t.match(/https?:\/\/[^\s<>"']+/i);
  return m ? m[0].replace(/[.,;:!?)\"']+$/, "") : t;
}

function currencyForUrl(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (host === "amzn.in" || host.endsWith(".amazon.in") || host.includes("flipkart")) return "₹";
    if (host.endsWith(".in") || host.includes("amazon.in") || host.includes("flipkart")) return "₹";
    if (host.endsWith(".co.uk") || host.endsWith(".uk")) return "£";
    if (host.endsWith(".de") || host.endsWith(".fr") || host.endsWith(".eu")) return "€";
    if (host.endsWith(".jp")) return "¥";
  } catch {
    /* ignore */
  }
  return "$";
}

function updateCurrencyHint() {
  const url = document.getElementById("productUrl")?.value.trim();
  const label = document.getElementById("targetPriceLabel");
  if (!label || !url) {
    if (label) label.textContent = "Notify when price drops below";
    return;
  }
  const cur = currencyForUrl(url);
  label.textContent = `Target price (${cur})`;
}

function formatMoney(amount, currency) {
  const c = currency || "₹";
  const locale = c === "₹" ? "en-IN" : undefined;
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  return (
    c +
    n.toLocaleString(locale, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })
  );
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function loadUserInfo() {
  fetch("/api/auth/me")
    .then((r) => r.json())
    .then((data) => {
      if (!data.logged_in) {
        window.location.href = "/price-tracker/login";
        return;
      }
      document.getElementById("currentUser").textContent = data.username;
      if (data.is_admin) {
        document.getElementById("adminBadge").classList.remove("hidden");
        document.getElementById("adminLink").classList.remove("hidden");
      }
    });
}

function logout() {
  fetch("/api/auth/logout", { method: "POST" }).then(() => {
    window.location.href = "/price-tracker/login";
  });
}

function testNotification() {
  const btn = document.getElementById("testNotifBtn");
  const result = document.getElementById("testNotifResult");
  btn.disabled = true;
  btn.textContent = "Sending…";
  result.textContent = "";
  result.classList.add("hidden");

  fetch("/api/price/test-notification", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      btn.disabled = false;
      btn.textContent = "Test Telegram";
      result.classList.remove("hidden");
      if (data.ok) {
        result.textContent = "Test message sent to your Telegram.";
        result.classList.remove("inline-hint-error");
      } else {
        const url = data.activate_url || "https://t.me/CallMeBot_txtbot?text=%2Fstart";
        result.innerHTML = `Could not send. <a href="${url}" target="_blank" rel="noopener" class="link-telegram">Open Telegram &amp; send /start</a> first.`;
        result.classList.add("inline-hint-error");
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Test Telegram";
      result.classList.remove("hidden");
      result.classList.add("inline-hint-error");
      result.textContent = "Request failed. Try again.";
    });
}

function trackProduct() {
  const url = extractUrlFromPaste(document.getElementById("productUrl").value);
  const targetPrice = document.getElementById("targetPrice").value;
  const checkInterval = parseInt(document.getElementById("checkInterval").value, 10);

  if (!url || !targetPrice) {
    showError("Please fill in both fields.");
    return;
  }

  const btn = document.getElementById("trackBtn");
  btn.disabled = true;
  btn.textContent = "Fetching price…";
  hideError();

  const status = document.getElementById("trackStatus");
  status.classList.add("hidden");

  fetch("/api/price/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: url,
      target_price: parseFloat(targetPrice),
      check_interval: checkInterval,
    }),
  })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      btn.disabled = false;
      btn.textContent = "Start tracking";

      if (!ok) {
        showError(data.error || "Failed to track product.");
        return;
      }

      status.classList.remove("hidden");
      const cur = data.currency || currencyForUrl(url);
      let msg = `<strong>${escapeHtml(data.name || "Product")}</strong> is now tracked every ${data.check_interval || 3} min.`;
      if (data.current_price !== null) {
        msg += ` Current price: <strong>${formatMoney(data.current_price, cur)}</strong>.`;
      } else {
        msg += " Could not detect the current price — we'll keep checking.";
      }
      if (data.already_below) {
        msg += ' <span class="price-alert">Already at or below your target.</span>';
      }
      status.innerHTML = msg;

      document.getElementById("productUrl").value = "";
      document.getElementById("targetPrice").value = "";
      updateCurrencyHint();

      loadProducts();
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Start tracking";
      showError("Network error. Please try again.");
    });
}

function loadProducts() {
  fetch("/api/price/products")
    .then((r) => r.json())
    .then((products) => {
      const container = document.getElementById("productsContainer");
      const empty = document.getElementById("emptyState");
      const count = document.getElementById("productCount");

      if (products.length === 0) {
        container.innerHTML = "";
        empty.classList.remove("hidden");
        count.textContent = "";
        return;
      }

      empty.classList.add("hidden");
      count.textContent = `${products.length} product${products.length !== 1 ? "s" : ""}`;
      container.innerHTML = products.map(renderProduct).join("");
    });
}

function renderProduct(p) {
  const cur = p.currency || currencyForUrl(p.url);
  const priceClass =
    p.current_price !== null && p.current_price <= p.target_price
      ? "price-below"
      : "price-above";

  const priceDisplay =
    p.current_price !== null ? formatMoney(p.current_price, cur) : "—";

  const lastChecked = p.last_checked
    ? timeAgo(new Date(p.last_checked))
    : "Never";

  const interval = p.check_interval || 3;

  let statusBadge;
  if (p.notified) {
    statusBadge = '<span class="badge badge-success">Alerted</span>';
  } else if (
    p.current_price !== null &&
    p.current_price <= p.target_price
  ) {
    statusBadge = '<span class="badge badge-success">Below target</span>';
  } else {
    statusBadge = '<span class="badge badge-tracking">Tracking</span>';
  }

  let chartSvg = "";
  if (p.price_history && p.price_history.length > 1) {
    const prices = p.price_history.map((h) => h.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const w = 200;
    const h = 40;
    const points = prices
      .map((price, i) => {
        const x = (i / (prices.length - 1)) * w;
        const y = h - ((price - min) / range) * h;
        return `${x},${y}`;
      })
      .join(" ");
    chartSvg = `<svg class="price-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${points}" fill="none" stroke="#6c5ce7" stroke-width="2"/>
    </svg>`;
  }

  let savingsHtml = "";
  if (p.current_price !== null) {
    const diff = p.current_price - p.target_price;
    if (diff > 0) {
      savingsHtml = `<p class="price-diff">${formatMoney(diff, cur)} above target</p>`;
    } else if (diff <= 0) {
      savingsHtml = `<p class="price-diff price-diff-good">${formatMoney(Math.abs(diff), cur)} below target</p>`;
    }
  }

  const safeName = escapeHtml(p.name || "Unknown Product");
  const safeUrl = escapeHtml(truncateUrl(p.url));
  const fullUrl = escapeHtml(p.url);

  return `
    <article class="product-card">
      <div class="product-main">
        <div class="product-header">
          <h4 class="product-title">${safeName}</h4>
          ${statusBadge}
        </div>
        <p class="product-url-line">
          <a href="${fullUrl}" target="_blank" rel="noopener noreferrer" class="product-url">${safeUrl}</a>
        </p>
        <div class="product-prices-grid">
          <div class="price-item">
            <span class="price-label">Current</span>
            <span class="price-value ${priceClass}">${priceDisplay}</span>
          </div>
          <div class="price-item">
            <span class="price-label">Target</span>
            <span class="price-value">${formatMoney(p.target_price, cur)}</span>
          </div>
        </div>
        ${savingsHtml}
        <div class="product-meta">
          <span>Checked ${lastChecked}</span>
          <span class="meta-sep" aria-hidden="true">·</span>
          <span>Every ${interval} min</span>
        </div>
        <div class="interval-edit">
          <label>Check every</label>
          <select onchange="updateInterval('${p.id}', this)">${intervalOptions(interval)}</select>
        </div>
        ${chartSvg}
      </div>
      <div class="product-actions">
        <button type="button" class="btn-small btn-secondary" onclick="checkNow('${p.id}', this)">Check now</button>
        <button type="button" class="btn-small btn-secondary" onclick="confirmDelete('${p.id}', ${JSON.stringify(p.name || "this product")})">Remove</button>
      </div>
    </article>
  `;
}

function intervalOptions(selected) {
  const sel = selected || 3;
  let html = "";
  for (let m = 2; m <= 60; m++) {
    html += `<option value="${m}"${m === sel ? " selected" : ""}>${m} min</option>`;
  }
  return html;
}

function updateInterval(productId, selectEl) {
  const interval = parseInt(selectEl.value, 10);
  fetch(`/api/price/update/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ check_interval: interval }),
  })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        showError(data.error || "Could not update interval.");
        loadProducts();
      }
    });
}

function timeAgo(date) {
  const seconds = Math.floor((new Date() - date) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function truncateUrl(url) {
  try {
    const u = new URL(url);
    let path = u.pathname;
    if (path.length > 36) path = path.substring(0, 36) + "…";
    return u.hostname + path;
  } catch {
    return url.length > 48 ? url.substring(0, 48) + "…" : url;
  }
}

function checkNow(productId, btn) {
  btn.disabled = true;
  btn.textContent = "Checking…";

  fetch(`/api/price/check/${productId}`, { method: "POST" })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      btn.disabled = false;
      btn.textContent = "Check now";

      if (!ok) {
        showError(data.error || "Could not check price.");
        return;
      }

      loadProducts();

      if (data.below_target) {
        const status = document.getElementById("trackStatus");
        status.classList.remove("hidden");
        const c = data.currency || "₹";
        status.innerHTML = `<span class="price-alert">Price is ${formatMoney(data.current_price, c)} — below your target of ${formatMoney(data.target_price, c)}.</span>`;
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Check now";
    });
}

function confirmDelete(productId, productName) {
  if (confirm(`Stop tracking "${productName}"?`)) {
    deleteProduct(productId);
  }
}

function deleteProduct(productId) {
  fetch(`/api/price/delete/${productId}`, { method: "DELETE" }).then(() =>
    loadProducts(),
  );
}

function showError(msg) {
  const el = document.getElementById("errorSection");
  document.getElementById("errorText").textContent = msg;
  el.classList.remove("hidden");
}

function hideError() {
  document.getElementById("errorSection").classList.add("hidden");
}
