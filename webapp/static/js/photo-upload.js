// Up ảnh kho: chọn file, kéo thả hoặc dán (Ctrl+V) ảnh từ clipboard.
// Cap 50 ảnh khớp MAX_FILES_PER_UPLOAD trong webapp/photos.py.
// Nén ảnh ngay trên trình duyệt (thu nhỏ 2000px + JPEG q82, khớp tham số
// nén của server) để 1 lần gửi được nhiều ảnh mà không chạm trần
// ~95MB/request của server (và trần 100MB của Cloudflare free).
// Không có JS thì form vẫn hoạt động bình thường qua ô chọn file.
(() => {
  'use strict';

  const MAX_FILES = 50;
  // Trần an toàn cuối cùng sau khi nén; server chỉ nhận 95MB/request.
  const MAX_TOTAL_BYTES = 90 * 1024 * 1024;
  // Khớp MAX_PIXELS / FULL_QUALITY trong webapp/services/photo_storage.py:
  // server cũng thu nhỏ + nén giống vậy nên ảnh nén client cho kết quả như nhau.
  const MAX_PIXELS = 2000;
  const JPEG_QUALITY = 0.82;
  // Ảnh nhỏ đã nhẹ thì gửi nguyên bản, không cần đụng canvas.
  const SKIP_COMPRESS_BYTES = 3 * 1024 * 1024;

  const input = document.getElementById('images');
  const zone = document.getElementById('dropzone');
  const grid = document.getElementById('paste-previews');
  const counter = document.getElementById('paste-count');
  if (!input || !zone || !grid || !counter) return;

  let files = [];
  let busy = false; // đang nén — chặn submit giữa chừng
  const urls = new Map(); // File -> objectURL, revoke khi bỏ ảnh để đỡ tốn RAM

  // Đồng bộ danh sách về input.files để submit như chọn file bình thường.
  // Trình duyệt quá cũ thiếu DataTransfer thì bỏ qua: chọn file vẫn chạy,
  // chỉ mất tính năng dán/xem trước.
  const canManage = (() => {
    try { new DataTransfer(); return true; } catch (_) { return false; }
  })();

  const syncInput = () => {
    if (!canManage) return;
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));
    input.files = dt.files;
  };

  const urlFor = (file) => {
    if (!urls.has(file)) urls.set(file, URL.createObjectURL(file));
    return urls.get(file);
  };

  const sameFile = (a, b) =>
    a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;

  const render = (message, warn) => {
    grid.textContent = '';
    files.forEach((file, i) => {
      const item = document.createElement('div');
      item.className = 'paste-item';

      const img = document.createElement('img');
      img.src = urlFor(file);
      img.alt = file.name || 'ảnh sẽ gửi';
      item.appendChild(img);

      const name = document.createElement('span');
      name.className = 'paste-item-name';
      name.textContent = file.name || 'ảnh dán';
      name.title = name.textContent;
      item.appendChild(name);

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'paste-item-remove';
      remove.setAttribute('aria-label', 'Bỏ ảnh này');
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        const url = urls.get(file);
        if (url) { URL.revokeObjectURL(url); urls.delete(file); }
        files.splice(i, 1);
        syncInput();
        render();
      });
      item.appendChild(remove);

      grid.appendChild(item);
    });
    counter.classList.toggle('warn', Boolean(warn));
    counter.textContent = message || (files.length
      ? `Đã chọn ${files.length}/${MAX_FILES} ảnh`
      : 'Chưa có ảnh nào');
  };

  // Decode ảnh bằng createImageBitmap; fallback qua <img> cho trình duyệt cũ.
  const decodeImage = (file) =>
    (window.createImageBitmap
      ? createImageBitmap(file)
      : new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => resolve(img);
          img.onerror = () => reject(new Error('decode failed'));
          img.src = URL.createObjectURL(file);
        }));

  // Nén 1 file về JPEG ≤2000px. Trả về chính file nếu decode lỗi
  // (kệ — server sẽ từ chối với thông báo rõ ràng) hoặc ảnh nhỏ sẵn.
  const compress = async (file) => {
    if (file.size <= SKIP_COMPRESS_BYTES) return file;
    let bitmap;
    try {
      bitmap = await decodeImage(file);
    } catch (_) {
      return file; // HEIC hoặc định dạng trình duyệt không đọc được — để server xử lý
    }
    try {
      const w = bitmap.width || bitmap.naturalWidth;
      const h = bitmap.height || bitmap.naturalHeight;
      if (!w || !h) return file;
      const scale = Math.min(1, MAX_PIXELS / Math.max(w, h));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      if (bitmap.close) bitmap.close();
      const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
      // Nén không lợi gì (hoặc hỏng) thì giữ bản gốc
      if (!blob || blob.size >= file.size) return file;
      const base = (file.name || 'anh').replace(/\.[^.]+$/, '');
      return new File([blob], `${base}.jpg`, { type: 'image/jpeg' });
    } catch (_) {
      return file;
    }
  };

  const totalBytes = () => files.reduce((sum, f) => sum + f.size, 0);

  const addFiles = async (fileList) => {
    const incoming = [...(fileList || [])]
      .filter((f) => f && f.type && f.type.startsWith('image/'));
    const fresh = incoming.filter((f) => !files.some((cur) => sameFile(cur, f)));
    if (!fresh.length) return;
    if (files.length >= MAX_FILES) {
      render(`Tối đa ${MAX_FILES} ảnh mỗi lần gửi — bỏ qua ${fresh.length} ảnh`, true);
      return;
    }

    busy = true;
    const accepted = [];
    let skipped = 0;
    for (let i = 0; i < fresh.length && files.length + accepted.length < MAX_FILES; i++) {
      render(`Đang nén ảnh ${i + 1}/${fresh.length}…`, true);
      const compressed = await compress(fresh[i]);
      if (totalBytes() + compressed.size > MAX_TOTAL_BYTES) {
        skipped += 1;
        continue;
      }
      accepted.push(compressed);
    }
    busy = false;

    if (accepted.length) files = files.concat(accepted);
    if (skipped) {
      render(`Tối đa ${MAX_FILES} ảnh, tổng ~90MB mỗi lần gửi — bỏ qua ${skipped} ảnh`, true);
    } else {
      render();
    }
    syncInput();
  };

  // Chọn qua ô nhập (cũng là lúc bấm vào dropzone)
  input.addEventListener('change', () => addFiles(input.files));

  // Lưới an toàn khi gửi: nếu tổng dung lượng vẫn vượt giới hạn thì chặn nộp,
  // tránh upload cả batch rồi nhận 413 từ server/proxy.
  const form = input.closest('form');
  if (form) {
    form.addEventListener('submit', (event) => {
      if (busy || totalBytes() > MAX_TOTAL_BYTES) {
        event.preventDefault();
        render(busy ? 'Đang nén ảnh, đợi chút rồi lưu nhé…'
                    : 'Tổng dung lượng ảnh quá lớn — mỗi lần gửi tối đa ~90MB, hãy bớt bớt ảnh', true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  // Dán ảnh từ clipboard (Ctrl+V) ở bất kỳ đâu trên trang.
  // Chỉ chặn hành vi mặc định khi thật sự có ảnh, để dán text vào ghi chú vẫn bình thường.
  document.addEventListener('paste', (event) => {
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) return;
    const images = [];
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) images.push(file);
      }
    }
    if (images.length) {
      event.preventDefault();
      addFiles(images);
    }
  });

  // Kéo thả ảnh vào dropzone
  ['dragenter', 'dragover'].forEach((type) =>
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add('dragover');
    }));
  ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, () => zone.classList.remove('dragover')));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    addFiles(event.dataTransfer && event.dataTransfer.files);
  });

  render();
})();
