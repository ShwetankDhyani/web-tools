document.addEventListener("DOMContentLoaded", () => {
  checkEmailConfig();
  loadProducts();
});

function checkEmailConfig() {
  fetch("/api/price/email-config")
    .then((r) => r.json())
    .then((data) => {
      const banner = document.getElementById("emailBanner");
      if (!data.configured) {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    });
}

function toggleEmailConfig() {
  const el = document.getElementById("emailConfig");
  el.classList.toggle("hidden");
}

function saveEmailConfig() {
  const btn = document.getElementById("saveEmailBtn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  fetch("/api/price/email-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      smtp_host: document.getElementById("smtpHost").value,
      smtp_port: parseInt(document.getElementById("smtpPort").value),
      smtp_user: document.getElementById("smtpUser").value,
      smtp_pass: document.getElementById("smtpPass").value,
    }),
  })
    .then((r) => r.json())
    .then(() => {
      btn.textContent = "Saved!";
      setTimeout(() => {
        btn.textContent = "Save";
        btn.disabled = false;
        toggleEmailConfig();
        checkEmailConfig();
      }, 1500);
    })
    .catch(() => {
      btn.textContent = "Save";
      btn.disabled = false;
    });
}

function trackProduct() {
  const url = document.getElementById("productUrl").value.trim();
  const targetPrice = document.getElementById("targetPrice").value;
  const email = document.getElementById("alertEmail").value.trim();

  if (!url || !targetPrice || !email) {
    showError("Please fill in all fields.");
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
      email: email,
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
      let msg = `<strong>${data.name || "Product"}</strong> is now being tracked.`;
      if (data.current_price !== null) {
        msg += ` Current price: <strong>$${data.current_price.toFixed(2)}</strong>.`;
      } else {
        msg += " Could not detect the current price — we'll keep checking.";
      }
      if (data.already_below) {
        msg +=
          ' <span class="price-alert">The price is already at or below your target!</span>';
      }
      status.innerHTML = msg;

      // Clear form
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

      if (products.length === 0) {
        container.innerHTML = "";
        empty.classList.remove("hidden");
        return;
      }

      empty.classList.add("hidden");
      container.innerHTML = products.map(renderProduct).join("");
    });
}

function renderProduct(p) {
  const priceClass =
    p.current_price !== null && p.current_price <= p.target_price
      ? "price-below"
      : "price-above";

  const priceDisplay =
    p.current_price !== null ? `$${p.current_price.toFixed(2)}` : "Unknown";

  const lastChecked = p.last_checked
    ? new Date(p.last_checked).toLocaleString()
    : "Never";

  const statusBadge = p.notified
    ? '<span class="badge badge-success">Notified</span>'
    : '<span class="badge badge-tracking">Tracking</span>';

  // Mini price chart using SVG
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
            <span class="price-value">$${p.target_price.toFixed(2)}</span>
          </div>
        </div>
        ${chartSvg}
        <div class="product-meta">
          <span>Last checked: ${lastChecked}</span>
          <span>Alert: ${p.email}</span>
        </div>
      </div>
      <div class="product-actions">
        <button class="btn-small btn-check" onclick="checkNow('${p.id}', this)">Check Now</button>
        <button class="btn-small btn-delete" onclick="deleteProduct('${p.id}')">Remove</button>
      </div>
    </div>
  `;
}

function truncateUrl(url) {
  try {
    const u = new URL(url);
    let path = u.pathname;
    if (path.length > 50) path = path.substring(0, 50) + "...";
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
        status.innerHTML = `<span class="price-alert">Price dropped to $${data.current_price.toFixed(2)} — below your target of $${data.target_price.toFixed(2)}!</span>`;
      }
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Check Now";
    });
}

function deleteProduct(productId) {
  fetch(`/api/price/delete/${productId}`, { method: "DELETE" })
    .then(() => loadProducts());
}

function showError(msg) {
  const el = document.getElementById("errorSection");
  document.getElementById("errorText").textContent = msg;
  el.classList.remove("hidden");
}

function hideError() {
  document.getElementById("errorSection").classList.add("hidden");
}
