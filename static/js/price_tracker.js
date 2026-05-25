document.addEventListener("DOMContentLoaded", () => {
  checkEmailConfig();
  checkWhatsAppConfig();
  loadProducts();
});

function checkEmailConfig() {
  fetch("/api/price/email-config")
    .then((r) => r.json())
    .then((data) => {
      const chip = document.getElementById("emailStatusText");
      if (data.configured) {
        chip.textContent = data.smtp_user;
        chip.parentElement.classList.add("configured");
      } else {
        chip.textContent = "not set";
        chip.parentElement.classList.remove("configured");
      }
      updateTestBtn();
    });
}

function toggleEmailConfig() {
  const el = document.getElementById("emailConfig");
  el.classList.toggle("hidden");
  document.getElementById("whatsappConfig").classList.add("hidden");
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

function checkWhatsAppConfig() {
  fetch("/api/price/whatsapp-config")
    .then((r) => r.json())
    .then((data) => {
      const chip = document.getElementById("msgStatusText");
      if (data.configured) {
        const label =
          data.platform === "telegram" ? "Telegram" : "WhatsApp";
        chip.textContent = label + ": " + data.phone;
        chip.parentElement.classList.add("configured");
      } else {
        chip.textContent = "not set";
        chip.parentElement.classList.remove("configured");
      }
      updateTestBtn();
    });
}

function updateTestBtn() {
  Promise.all([
    fetch("/api/price/email-config").then((r) => r.json()),
    fetch("/api/price/whatsapp-config").then((r) => r.json()),
  ]).then(([email, msg]) => {
    const btn = document.getElementById("testNotifBtn");
    btn.style.display =
      email.configured || msg.configured ? "inline-flex" : "none";
  });
}

function testNotifications() {
  const btn = document.getElementById("testNotifBtn");
  const result = document.getElementById("testNotifResult");
  btn.disabled = true;
  btn.textContent = "Sending...";
  result.textContent = "";

  fetch("/api/price/test-notification", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel: "all" }),
  })
    .then((r) => r.json())
    .then((data) => {
      btn.disabled = false;
      btn.textContent = "Test Alert";
      const parts = [];
      if (data.results.email === true) parts.push("Email sent");
      else if (data.results.email === false) parts.push("Email failed");
      else if (data.results.email === "not_configured")
        parts.push("Email not configured");
      if (data.results.messaging === true) parts.push("Message sent");
      else if (data.results.messaging === false) parts.push("Message failed");
      result.textContent = parts.join(" · ") || "No channels configured";
      result.style.color =
        data.results.email === true || data.results.messaging === true
          ? "var(--accent)"
          : "#e74c3c";
    })
    .catch(() => {
      btn.disabled = false;
      btn.textContent = "Test Alert";
      result.textContent = "Request failed";
      result.style.color = "#e74c3c";
    });
}

function toggleWhatsAppConfig() {
  const el = document.getElementById("whatsappConfig");
  el.classList.toggle("hidden");
  document.getElementById("emailConfig").classList.add("hidden");
}

function switchPlatform(platform) {
  document.getElementById("waPlatform").value = platform;
  document
    .getElementById("tabWhatsApp")
    .classList.toggle("active", platform === "whatsapp");
  document
    .getElementById("tabTelegram")
    .classList.toggle("active", platform === "telegram");
  document
    .getElementById("whatsappSetup")
    .classList.toggle("hidden", platform !== "whatsapp");
  document
    .getElementById("telegramSetup")
    .classList.toggle("hidden", platform !== "telegram");

  const phoneLabel = document.getElementById("waPhoneLabel");
  const phoneInput = document.getElementById("waPhone");
  const apiKeyField = document
    .getElementById("waApiKey")
    .closest(".config-field");

  if (platform === "telegram") {
    phoneLabel.textContent = "Telegram Username (without @)";
    phoneInput.placeholder = "your_username";
    apiKeyField.style.display = "none";
  } else {
    phoneLabel.textContent = "Phone Number (with country code)";
    phoneInput.placeholder = "+919876543210";
    apiKeyField.style.display = "";
  }
}

function saveWhatsAppConfig() {
  const btn = document.getElementById("saveWhatsAppBtn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  const platform = document.getElementById("waPlatform").value;

  fetch("/api/price/whatsapp-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone: document.getElementById("waPhone").value,
      api_key: document.getElementById("waApiKey").value || "telegram",
      enabled: true,
      platform: platform,
    }),
  })
    .then((r) => r.json())
    .then(() => {
      btn.textContent = "Saved!";
      setTimeout(() => {
        btn.textContent = "Save";
        btn.disabled = false;
        toggleWhatsAppConfig();
        checkWhatsAppConfig();
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

  const priceDisplay =
    p.current_price !== null ? `$${p.current_price.toFixed(2)}` : "—";

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
      ? `<span class="price-diff">$${savings} above target</span>`
      : savings !== null && parseFloat(savings) <= 0
        ? `<span class="price-diff price-diff-good">$${Math.abs(parseFloat(savings)).toFixed(2)} below target</span>`
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
            <span class="price-value">$${p.target_price.toFixed(2)}</span>
          </div>
          <div class="price-item price-item-info">
            ${savingsHtml}
          </div>
        </div>
        ${chartSvg}
        <div class="product-meta">
          <span>Checked ${lastChecked}</span>
          <span>Alerts to ${p.email}</span>
        </div>
      </div>
      <div class="product-actions">
        <button class="btn-small btn-check" onclick="checkNow('${p.id}', this)" title="Check price now">Check Now</button>
        <button class="btn-small btn-delete" onclick="confirmDelete('${p.id}', '${(p.name || "this product").replace(/'/g, "\\'")}')" title="Stop tracking">Remove</button>
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
        status.innerHTML = `<span class="price-alert">Price dropped to $${data.current_price.toFixed(2)} — below your target of $${data.target_price.toFixed(2)}!</span>`;
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
