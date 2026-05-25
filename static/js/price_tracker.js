document.addEventListener("DOMContentLoaded", () => {
  loadUserInfo();
  loadProducts();
});

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
        document.getElementById("adminLink").style.display = "";
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
  btn.textContent = "Sending...";
  result.textContent = "";

  fetch("/api/price/test-notification", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      btn.disabled = false;
      btn.textContent = "Test Alert";
      if (data.ok) {
        result.textContent = "Test message sent to your Telegram!";
        result.style.color = "var(--accent)";
      } else {
        result.textContent =
          "Failed — make sure you messaged @CallMeBot_txtbot with /start first";
        result.style.color = "#e74c3c";
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Test Alert";
      result.textContent = "Request failed";
      result.style.color = "#e74c3c";
    });
}

function trackProduct() {
  const url = document.getElementById("productUrl").value.trim();
  const targetPrice = document.getElementById("targetPrice").value;

  if (!url || !targetPrice) {
    showError("Please fill in both fields.");
    return;
  }

  const btn = document.getElementById("trackBtn");
  btn.disabled = true;
  btn.textContent = "Fetching price...";
  hideError();

  const status = document.getElementById("trackStatus");
  status.classList.add("hidden");

  fetch("/api/price/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: url,
      target_price: parseFloat(targetPrice),
    }),
  })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      btn.disabled = false;
      btn.textContent = "Start Tracking";

      if (!ok) {
        showError(data.error || "Failed to track product.");
        return;
      }

      status.classList.remove("hidden");
      const cur = data.currency || "$";
      let msg = `<strong>${data.name || "Product"}</strong> is now being tracked.`;
      if (data.current_price !== null) {
        msg += ` Current price: <strong>${cur}${data.current_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong>.`;
      } else {
        msg += " Could not detect the current price — we'll keep checking.";
      }
      if (data.already_below) {
        msg +=
          ' <span class="price-alert">The price is already at or below your target!</span>';
      }
      status.innerHTML = msg;

      document.getElementById("productUrl").value = "";
      document.getElementById("targetPrice").value = "";

      loadProducts();
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Start Tracking";
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
  const priceClass =
    p.current_price !== null && p.current_price <= p.target_price
      ? "price-below"
      : "price-above";

  const cur = p.currency || "$";
  const priceDisplay =
    p.current_price !== null ? `${cur}${p.current_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "—";

  const lastChecked = p.last_checked
    ? timeAgo(new Date(p.last_checked))
    : "Never";

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
    chartSvg = `<svg class="price-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="#6c5ce7" stroke-width="2"/>
    </svg>`;
  }

  const savings =
    p.current_price !== null
      ? (p.current_price - p.target_price).toFixed(2)
      : null;
  const savingsHtml =
    savings !== null && parseFloat(savings) > 0
      ? `<span class="price-diff">${cur}${parseFloat(savings).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} above target</span>`
      : savings !== null && parseFloat(savings) <= 0
        ? `<span class="price-diff price-diff-good">${cur}${Math.abs(parseFloat(savings)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} below target</span>`
        : "";

  return `
    <div class="product-card">
      <div class="product-info">
        <div class="product-header">
          <h4>${p.name || "Unknown Product"}</h4>
          ${statusBadge}
        </div>
        <a href="${p.url}" target="_blank" rel="noopener" class="product-url">${truncateUrl(p.url)}</a>
        <div class="product-prices">
          <div class="price-item">
            <span class="price-label">Current</span>
            <span class="price-value ${priceClass}">${priceDisplay}</span>
          </div>
          <div class="price-item">
            <span class="price-label">Target</span>
            <span class="price-value">${cur}${p.target_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
          </div>
          ${savingsHtml}
        </div>
        <div class="product-meta">
          <span>Checked ${lastChecked}</span>
        </div>
        ${chartSvg}
      </div>
      <div class="product-actions">
        <button class="btn-small btn-secondary" onclick="checkNow('${p.id}', this)" title="Check price now">Check Now</button>
        <button class="btn-small btn-secondary" onclick="confirmDelete('${p.id}', '${(p.name || "this product").replace(/'/g, "\\'")}')" title="Stop tracking">Remove</button>
      </div>
    </div>
  `;
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
    if (path.length > 40) path = path.substring(0, 40) + "...";
    return u.hostname + path;
  } catch {
    return url.length > 60 ? url.substring(0, 60) + "..." : url;
  }
}

function checkNow(productId, btn) {
  btn.disabled = true;
  btn.textContent = "Checking...";

  fetch(`/api/price/check/${productId}`, { method: "POST" })
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      btn.disabled = false;
      btn.textContent = "Check Now";

      if (!ok) {
        showError(data.error || "Could not check price.");
        return;
      }

      loadProducts();

      if (data.below_target) {
        const status = document.getElementById("trackStatus");
        status.classList.remove("hidden");
        const c = data.currency || "$";
        status.innerHTML = `<span class="price-alert">Price dropped to ${c}${data.current_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} — below your target of ${c}${data.target_price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}!</span>`;
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Check Now";
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
