/* ============================================================
   Stellar Exchange — main.js
   Web3 wallet, Stripe checkout, market data ticker, UI helpers
   ============================================================ */

(function () {
  'use strict';

  // ----------------------------------------------------------------
  // STARFIELD GENERATOR
  // ----------------------------------------------------------------
  function initStarfield() {
    const container = document.getElementById('starfield');
    if (!container) return;
    const count = 180;
    for (let i = 0; i < count; i++) {
      const star = document.createElement('div');
      star.className = 'star';
      const size = Math.random() * 2.5 + 0.5;
      star.style.cssText = `
        width:${size}px; height:${size}px;
        top:${Math.random() * 100}%;
        left:${Math.random() * 100}%;
        animation-duration:${Math.random() * 4 + 2}s;
        animation-delay:${Math.random() * 6}s;
      `;
      container.appendChild(star);
    }
  }

  // ----------------------------------------------------------------
  // WEB3 / METAMASK WALLET
  // ----------------------------------------------------------------
  const WALLET_KEY = 'stellar_wallet_address';

  async function connectWallet() {
    const btn = document.getElementById('wallet-btn');
    if (!window.ethereum) {
      alert('MetaMask is not installed. Please install MetaMask to connect a wallet.');
      return;
    }
    try {
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      if (accounts.length > 0) {
        const addr = accounts[0];
        localStorage.setItem(WALLET_KEY, addr);
        updateWalletUI(addr);
        document.dispatchEvent(new CustomEvent('walletConnected', { detail: { address: addr } }));
      }
    } catch (err) {
      console.error('Wallet connection failed:', err);
      if (err.code !== 4001) {
        alert('Failed to connect wallet: ' + (err.message || err));
      }
    }
  }

  function disconnectWallet() {
    localStorage.removeItem(WALLET_KEY);
    updateWalletUI(null);
  }

  function getConnectedWallet() {
    return localStorage.getItem(WALLET_KEY);
  }

  function truncateAddress(addr) {
    if (!addr) return '';
    return addr.slice(0, 6) + '...' + addr.slice(-4);
  }

  function updateWalletUI(address) {
    const btn = document.getElementById('wallet-btn');
    if (!btn) return;
    if (address) {
      btn.textContent = '🟢 ' + truncateAddress(address);
      btn.title = address;
    } else {
      btn.textContent = '🔌 Connect Wallet';
      btn.title = '';
    }
  }

  function initWallet() {
    const btn = document.getElementById('wallet-btn');
    if (!btn) return;

    const stored = getConnectedWallet();
    if (stored) updateWalletUI(stored);

    btn.addEventListener('click', () => {
      const addr = getConnectedWallet();
      if (addr) {
        if (confirm('Disconnect wallet ' + truncateAddress(addr) + '?')) {
          disconnectWallet();
        }
      } else {
        connectWallet();
      }
    });

    if (window.ethereum) {
      window.ethereum.on('accountsChanged', (accounts) => {
        if (accounts.length === 0) {
          disconnectWallet();
        } else {
          const addr = accounts[0];
          localStorage.setItem(WALLET_KEY, addr);
          updateWalletUI(addr);
        }
      });
    }
  }

  // ----------------------------------------------------------------
  // STRIPE CHECKOUT
  // ----------------------------------------------------------------
  async function initStripeCheckout(contractId, amount) {
    try {
      const res = await fetch('/api/create-checkout-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contract_id: contractId, amount: amount }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      } else if (data.error) {
        showToast('Payment error: ' + data.error, 'danger');
      }
    } catch (err) {
      showToast('Network error. Please try again.', 'danger');
    }
  }

  // ----------------------------------------------------------------
  // CRYPTO PURCHASE MODAL
  // ----------------------------------------------------------------
  function openCryptoModal(contractId) {
    const modal = document.getElementById('crypto-modal');
    if (!modal) return;
    document.getElementById('crypto-contract-id').value = contractId;
    const wallet = getConnectedWallet();
    if (wallet) {
      const walletField = document.getElementById('crypto-wallet-input');
      if (walletField) walletField.value = wallet;
    }
    modal.classList.add('active');
  }

  function closeCryptoModal() {
    const modal = document.getElementById('crypto-modal');
    if (modal) modal.classList.remove('active');
  }

  async function submitCryptoPurchase() {
    const contractId = parseInt(document.getElementById('crypto-contract-id').value);
    const txHash = document.getElementById('crypto-tx-hash').value.trim();
    const wallet = document.getElementById('crypto-wallet-input').value.trim();

    if (!txHash) { showToast('Please enter a transaction hash.', 'danger'); return; }
    if (!wallet) { showToast('Please enter your wallet address.', 'danger'); return; }

    try {
      const res = await fetch('/api/crypto-purchase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contract_id: contractId, tx_hash: txHash, buyer_wallet: wallet }),
      });
      const data = await res.json();
      if (data.status === 'ok') {
        closeCryptoModal();
        showToast('Transaction recorded! Contract marked as filled.', 'success');
        setTimeout(() => location.reload(), 2000);
      } else {
        showToast('Error: ' + (data.error || 'Unknown error'), 'danger');
      }
    } catch (err) {
      showToast('Network error. Please try again.', 'danger');
    }
  }

  // ----------------------------------------------------------------
  // MARKET DATA TICKER
  // ----------------------------------------------------------------
  let marketDataCache = {};

  async function fetchMarketData() {
    try {
      const res = await fetch('/api/market-data');
      const data = await res.json();
      marketDataCache = data;
      updateTickerUI(data);
      updatePricePreviews(data);
    } catch (err) {
      console.warn('Market data fetch failed:', err);
    }
  }

  function updateTickerUI(data) {
    document.querySelectorAll('[data-ticker-slug]').forEach(el => {
      const slug = el.dataset.tickerSlug;
      const field = el.dataset.tickerField;
      if (!data[slug]) return;
      const item = data[slug];
      if (field === 'price') {
        const formatted = '$' + item.current_price_usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        animateValue(el, formatted);
      } else if (field === 'change') {
        const change = item.price_change_24h;
        const sign = change >= 0 ? '+' : '';
        el.textContent = sign + change.toFixed(2) + '%';
        el.className = 'ticker-change ' + (change >= 0 ? 'up' : 'down');
      }
    });
  }

  function animateValue(el, newVal) {
    if (el.textContent === newVal) return;
    el.style.transition = 'opacity 0.3s';
    el.style.opacity = '0';
    setTimeout(() => {
      el.textContent = newVal;
      el.style.opacity = '1';
    }, 300);
  }

  function updatePricePreviews(data) {
    document.querySelectorAll('[data-market-slug]').forEach(el => {
      const slug = el.dataset.marketSlug;
      if (data[slug]) {
        el.textContent = '$' + data[slug].current_price_usd.toLocaleString('en-US', { minimumFractionDigits: 2 }) + ' / ' + data[slug].unit;
      }
    });
  }

  function initMarketTicker() {
    fetchMarketData();
    setInterval(fetchMarketData, 30000);
  }

  // ----------------------------------------------------------------
  // CONTRACT FILTERING (marketplace)
  // ----------------------------------------------------------------
  function initFilters() {
    const form = document.getElementById('filter-form');
    if (!form) return;
    form.querySelectorAll('select').forEach(sel => {
      sel.addEventListener('change', () => form.submit());
    });
    const resetBtn = document.getElementById('reset-filters');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        form.querySelectorAll('select').forEach(s => s.value = '');
        form.submit();
      });
    }
  }

  // ----------------------------------------------------------------
  // CATEGORY PRICE PREVIEW (create contract form)
  // ----------------------------------------------------------------
  function initCategoryPreview() {
    const catSelect = document.getElementById('category-select');
    const preview = document.getElementById('price-preview');
    const unitField = document.getElementById('unit-display');
    if (!catSelect || !preview) return;

    catSelect.addEventListener('change', async () => {
      const slug = catSelect.options[catSelect.selectedIndex]?.dataset?.slug;
      if (!slug) { preview.classList.remove('visible'); return; }

      if (marketDataCache[slug]) {
        showPricePreview(marketDataCache[slug], preview, unitField);
      } else {
        try {
          const res = await fetch('/api/market-data');
          const data = await res.json();
          marketDataCache = data;
          if (data[slug]) showPricePreview(data[slug], preview, unitField);
        } catch (e) {
          console.warn('Failed to fetch market data for preview');
        }
      }
    });
  }

  function showPricePreview(item, preview, unitField) {
    const priceEl = preview.querySelector('.preview-price');
    if (priceEl) {
      priceEl.textContent = '$' + item.current_price_usd.toLocaleString('en-US', { minimumFractionDigits: 2 }) + ' / ' + item.unit;
    }
    if (unitField) unitField.textContent = item.unit;
    preview.classList.add('visible');
  }

  // ----------------------------------------------------------------
  // CREATE CONTRACT FORM VALIDATION
  // ----------------------------------------------------------------
  function initCreateForm() {
    const form = document.getElementById('create-contract-form');
    if (!form) return;
    form.addEventListener('submit', (e) => {
      const title = form.querySelector('[name="title"]').value.trim();
      const qty = parseFloat(form.querySelector('[name="resource_quantity"]').value);
      const strike = parseFloat(form.querySelector('[name="strike_price_usd"]').value);
      const premium = parseFloat(form.querySelector('[name="premium_usd"]').value);
      const expiry = form.querySelector('[name="expiry_date"]').value;
      const wallet = form.querySelector('[name="seller_wallet"]').value.trim();
      const errors = [];

      if (!title) errors.push('Title is required.');
      if (!qty || qty <= 0) errors.push('Resource quantity must be positive.');
      if (!strike || strike <= 0) errors.push('Strike price must be positive.');
      if (!premium || premium < 0) errors.push('Premium must be non-negative.');
      if (!expiry) errors.push('Expiry date is required.');
      else if (new Date(expiry) <= new Date()) errors.push('Expiry date must be in the future.');
      if (!wallet) errors.push('Seller wallet address is required.');
      else if (!/^0x[0-9a-fA-F]{40}$/.test(wallet)) errors.push('Seller wallet must be a valid Ethereum address (0x...).');

      if (errors.length > 0) {
        e.preventDefault();
        showToast(errors[0], 'danger');
      }
    });
  }

  // ----------------------------------------------------------------
  // WALLET PAGE
  // ----------------------------------------------------------------
  function initWalletPage() {
    const connectBig = document.getElementById('connect-wallet-big');
    if (!connectBig) return;

    const stored = getConnectedWallet();
    const display = document.getElementById('wallet-address-display');
    if (stored) {
      connectBig.textContent = 'Disconnect Wallet';
      if (display) display.textContent = stored;
    }

    connectBig.addEventListener('click', async () => {
      const current = getConnectedWallet();
      if (current) {
        disconnectWallet();
        connectBig.textContent = 'Connect MetaMask Wallet';
        if (display) display.textContent = '—';
      } else {
        await connectWallet();
        const addr = getConnectedWallet();
        if (addr) {
          connectBig.textContent = 'Disconnect Wallet';
          if (display) display.textContent = addr;
        }
      }
    });
  }

  // ----------------------------------------------------------------
  // TOAST NOTIFICATIONS
  // ----------------------------------------------------------------
  function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem;';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'alert alert-' + type;
    toast.style.cssText = 'min-width:280px;max-width:400px;animation:slideIn 0.3s ease;box-shadow:0 4px 20px rgba(0,0,0,0.4);';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.4s';
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  }

  // ----------------------------------------------------------------
  // URL PARAM FEEDBACK
  // ----------------------------------------------------------------
  function checkUrlFeedback() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('payment') === 'success') {
      showToast('Payment successful! Contract has been filled.', 'success');
    } else if (params.get('payment') === 'cancelled') {
      showToast('Payment cancelled. No charges were made.', 'warning');
    }
  }

  // ----------------------------------------------------------------
  // GLOBAL BUTTON WIRE-UP (data-action attributes)
  // ----------------------------------------------------------------
  function initGlobalActions() {
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      const contractId = btn.dataset.contractId ? parseInt(btn.dataset.contractId) : null;
      const amount = btn.dataset.amount ? parseFloat(btn.dataset.amount) : null;

      switch (action) {
        case 'stripe-checkout':
          initStripeCheckout(contractId, amount);
          break;
        case 'open-crypto-modal':
          openCryptoModal(contractId);
          break;
        case 'close-crypto-modal':
          closeCryptoModal();
          break;
        case 'submit-crypto':
          submitCryptoPurchase();
          break;
      }
    });
  }

  // ----------------------------------------------------------------
  // INITIALIZE
  // ----------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    initStarfield();
    initWallet();
    initMarketTicker();
    initFilters();
    initCategoryPreview();
    initCreateForm();
    initWalletPage();
    initGlobalActions();
    checkUrlFeedback();
  });

  // Expose helpers globally for inline use
  window.StellarExchange = {
    connectWallet,
    disconnectWallet,
    getConnectedWallet,
    truncateAddress,
    initStripeCheckout,
    openCryptoModal,
    closeCryptoModal,
    showToast,
  };
})();
