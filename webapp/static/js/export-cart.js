(() => {
  'use strict';

  const STORAGE_KEY = 'kho-export-cart-v1';

  const readCart = () => {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(parsed) ? parsed.filter(x => x && Number.isInteger(x.product_id)) : [];
    } catch (_) {
      return [];
    }
  };

  // Xuất kho xong thì trang thành công gọi hàm này. Nếu không xóa, giỏ hàng cũ
  // còn nguyên và lần bấm "Tiếp tục" tiếp theo sẽ xuất trùng hoặc lỗi hết hàng.
  window.KhoExportCart = {
    clear() { sessionStorage.removeItem(STORAGE_KEY); },
  };

  const lines = document.querySelector('#cart-lines');
  if (!lines) return;

  let cart = readCart();
  const cards = new Map();
  document.querySelectorAll('.export-product-card').forEach(card => {
    cards.set(Number(card.dataset.productId), card);
  });

  const notice = document.querySelector('#cart-notice');
  const showNotice = message => {
    if (!notice) return;
    notice.textContent = message || '';
    notice.hidden = !message;
  };

  const save = () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    render();
  };

  // Phản hồi "đã thêm" bằng cách đổi text node, không gán lại HTML của nút
  const flashAdded = button => {
    const label = button.querySelector('.btn-add-label') || button;
    if (button.dataset.flashing === '1') return;
    button.dataset.flashing = '1';
    const original = label.textContent;
    label.textContent = 'Đã thêm ✓';
    button.classList.add('btn-success');
    setTimeout(() => {
      label.textContent = original;
      button.classList.remove('btn-success');
      delete button.dataset.flashing;
    }, 1000);
  };

  const render = () => {
    lines.textContent = '';

    if (cart.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.className = 'cart-empty';
      const emptyP = document.createElement('p');
      emptyP.textContent = 'Chưa có sản phẩm nào';
      const emptySmall = document.createElement('small');
      emptySmall.className = 'text-muted';
      emptySmall.textContent = 'Chọn sản phẩm để thêm';
      emptyDiv.append(emptyP, emptySmall);
      lines.append(emptyDiv);
    } else {
      cart.forEach(item => {
        const row = document.createElement('div');
        row.className = 'cart-line';

        const info = document.createElement('div');
        info.className = 'cart-line-info';

        const name = document.createElement('span');
        name.className = 'cart-line-name';
        name.textContent = item.name;

        const qty = document.createElement('input');
        qty.type = 'number';
        qty.className = 'cart-line-qty-input';
        qty.min = '1';
        qty.max = String(item.stock);
        qty.value = String(item.quantity);
        qty.setAttribute('aria-label', `Số lượng ${item.name}`);
        // Sửa số lượng ngay trong phiếu, không phải quay lại thẻ sản phẩm
        qty.addEventListener('change', () => {
          const wanted = Math.trunc(Number(qty.value));
          if (!Number.isFinite(wanted) || wanted < 1) {
            qty.value = String(item.quantity);
            return;
          }
          if (wanted > item.stock) {
            item.quantity = item.stock;
            showNotice(`${item.name} chỉ còn ${item.stock} ${item.unit}.`);
          } else {
            item.quantity = wanted;
            showNotice('');
          }
          save();
        });

        const unit = document.createElement('span');
        unit.className = 'cart-line-unit';
        unit.textContent = item.unit;

        info.append(name, qty, unit);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'icon-button';
        remove.textContent = '×';
        remove.title = `Bỏ ${item.name} khỏi phiếu`;
        remove.addEventListener('click', () => {
          // Tìm theo product_id, không theo chỉ số mảng
          cart = cart.filter(x => x.product_id !== item.product_id);
          showNotice('');
          save();
        });

        row.append(info, remove);
        lines.append(row);
      });
    }

    const cartCount = document.querySelector('#cart-count');
    if (cartCount) cartCount.textContent = String(cart.length);

    const itemsJson = document.querySelector('#items-json');
    if (itemsJson) {
      itemsJson.value = JSON.stringify(
        cart.map(({product_id, quantity}) => ({product_id, quantity}))
      );
    }

    const continueBtn = document.querySelector('#continue');
    if (continueBtn) continueBtn.disabled = cart.length === 0;

    const dockItems = document.querySelector('#dock-items');
    const dockUnits = document.querySelector('#dock-units');
    if (dockItems) dockItems.textContent = String(cart.length);
    if (dockUnits) {
      dockUnits.textContent = String(cart.reduce((sum, x) => sum + x.quantity, 0));
    }
  };

  /* Phiếu dạng bottom sheet cho màn hình hẹp */
  const dock = document.querySelector('#cart-dock');
  const backdrop = document.querySelector('#cart-backdrop');
  const closeBtn = document.querySelector('#cart-close');

  const setSheetOpen = open => {
    document.body.classList.toggle('cart-open', open);
    if (backdrop) backdrop.hidden = !open;
    if (dock) dock.setAttribute('aria-expanded', String(open));
    if (open && closeBtn) closeBtn.focus();
    else if (!open && dock) dock.focus();
  };

  if (dock) dock.addEventListener('click', () => setSheetOpen(true));
  if (closeBtn) closeBtn.addEventListener('click', () => setSheetOpen(false));
  if (backdrop) backdrop.addEventListener('click', () => setSheetOpen(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.body.classList.contains('cart-open')) {
      setSheetOpen(false);
    }
  });

  // Nhấp nháy dock khi vừa thêm hàng — trên mobile đây là phản hồi duy nhất thấy được
  const pulseDock = () => {
    if (!dock || dock.dataset.pulsing === '1') return;
    dock.dataset.pulsing = '1';
    dock.classList.add('is-updated');
    setTimeout(() => {
      dock.classList.remove('is-updated');
      delete dock.dataset.pulsing;
    }, 600);
  };

  /* Đối chiếu giỏ hàng với tồn kho hiện tại. Giỏ nằm trong sessionStorage nên có
     thể đã cũ: người khác vừa xuất mặt hàng đó, hoặc sản phẩm đã bị xóa. Không
     kiểm tra thì người dùng bấm "Tiếp tục" và nhận trang lỗi 400 trắng. */
  const reconcile = async () => {
    if (!cart.length) return;
    let stockById;
    try {
      const response = await fetch('/api/products', {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      stockById = new Map(data.products.map(p => [p.id, p]));
    } catch (_) {
      return;   // mất mạng thì cứ để server chặn, không tự xóa giỏ của người ta
    }

    const dropped = [];
    const clamped = [];
    cart = cart.filter(item => {
      const fresh = stockById.get(item.product_id);
      if (!fresh || fresh.quantity < 1) {
        dropped.push(item.name);
        return false;
      }
      item.name = fresh.name;
      item.unit = fresh.unit;
      item.stock = fresh.quantity;
      if (item.quantity > fresh.quantity) {
        item.quantity = fresh.quantity;
        clamped.push(`${fresh.name} còn ${fresh.quantity} ${fresh.unit}`);
      }
      return true;
    });

    const messages = [];
    if (dropped.length) messages.push(`Đã bỏ khỏi phiếu vì hết hàng: ${dropped.join(', ')}.`);
    if (clamped.length) messages.push(`Đã giảm theo tồn kho hiện tại: ${clamped.join('; ')}.`);
    if (messages.length) showNotice(messages.join(' '));
    save();
  };

  // Thẻ sản phẩm
  cards.forEach(card => {
    const input = card.querySelector('.quantity-input');
    const minusBtn = card.querySelector('[data-minus]');
    const plusBtn = card.querySelector('[data-plus]');
    const addBtn = card.querySelector('[data-add]');
    if (!input || !minusBtn || !plusBtn || !addBtn) return;

    const stock = Number(card.dataset.stock);
    const clamp = value => Math.max(1, Math.min(stock, value));

    const syncButtons = () => {
      const current = Number(input.value);
      minusBtn.disabled = current <= 1;
      plusBtn.disabled = current >= stock;
    };

    const setQuantity = value => {
      input.value = String(clamp(value));
      syncButtons();
    };

    minusBtn.addEventListener('click', () => setQuantity(Number(input.value) - 1));
    plusBtn.addEventListener('click', () => setQuantity(Number(input.value) + 1));

    // Nhập tay: chỉ chốt lại khi rời ô, để còn gõ được số nhiều chữ số
    input.addEventListener('input', syncButtons);
    input.addEventListener('change', () => {
      const wanted = Math.trunc(Number(input.value));
      setQuantity(Number.isFinite(wanted) && wanted >= 1 ? wanted : 1);
    });

    addBtn.addEventListener('click', () => {
      const wanted = Math.trunc(Number(input.value));
      if (!Number.isFinite(wanted) || wanted < 1) {
        showNotice('Nhập số lượng từ 1 trở lên.');
        setQuantity(1);
        return;
      }

      const productId = Number(card.dataset.productId);
      const existing = cart.find(x => x.product_id === productId);
      // "Thêm vào phiếu" là cộng dồn. Gán thẳng sẽ âm thầm bỏ số đã thêm trước đó.
      const total = (existing ? existing.quantity : 0) + wanted;

      if (total > stock) {
        showNotice(`${card.dataset.name} chỉ còn ${stock} ${card.dataset.unit}, phiếu đã lấy tối đa.`);
      } else {
        showNotice('');
      }
      const capped = Math.min(total, stock);

      if (existing) {
        existing.quantity = capped;
      } else {
        cart.push({
          product_id: productId,
          quantity: capped,
          name: card.dataset.name,
          sku: card.dataset.sku,
          unit: card.dataset.unit,
          stock,
        });
      }

      save();
      setQuantity(1);
      flashAdded(addBtn);
      pulseDock();
    });

    syncButtons();
  });

  const reviewForm = document.querySelector('#review-form');
  if (reviewForm) {
    reviewForm.addEventListener('submit', event => {
      if (!cart.length) {
        event.preventDefault();
        showNotice('Thêm ít nhất một mặt hàng vào phiếu trước khi tiếp tục.');
      }
    });
  }

  render();
  reconcile();
})();
