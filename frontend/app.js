/* =========================================================
   BlurTrace — Convert to Blur page logic
   Talks to the FastAPI backend at /api/process and /api/store
   (relative paths, since the backend serves this file itself).
   ========================================================= */

(function () {
  // Only run this logic on the Convert page (guards against app.js
  // being reused/loaded on other pages that don't have these elements).
  const dropzone = document.getElementById('dropzone');
  if (!dropzone) return;

  const fileInput = document.getElementById('file-input');
  const browseBtn = document.getElementById('browse-btn');
  const fileListEl = document.getElementById('file-list');
  const emptyHint = document.getElementById('empty-hint');

  const originalBoard = document.getElementById('original-board');
  const blurredBoard = document.getElementById('blurred-board');

  const btnGaussian = document.getElementById('btn-gaussian');
  const btnPixelate = document.getElementById('btn-pixelate');
  const intensitySlider = document.getElementById('intensity-slider');
  const intensityLevel = document.getElementById('intensity-level');

  const btnCopy = document.getElementById('btn-copy');
  const btnSave = document.getElementById('btn-save');
  const statusMsg = document.getElementById('status-msg');

  // ---- State -------------------------------------------------------------
  // files: [{ id, name, size, file (Blob), objectUrl }]
  let files = [];
  let activeFileId = null;
  let currentMethod = null;       // "gaussian" | "pixelate"
  let currentBlurredBase64 = null;
  let currentBlurredHash = null;
  let debounceTimer = null;

  function activeFile() {
    return files.find(f => f.id === activeFileId) || null;
  }

  function setStatus(text, kind) {
    statusMsg.textContent = text || '';
    statusMsg.className = 'status-msg' + (kind ? ' ' + kind : '');
    if (text) {
      clearTimeout(setStatus._t);
      setStatus._t = setTimeout(() => { statusMsg.textContent = ''; statusMsg.className = 'status-msg'; }, 4000);
    }
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  // ---- File list rendering ------------------------------------------------
  function renderFileList() {
    fileListEl.innerHTML = '';
    emptyHint.style.display = files.length === 0 ? 'block' : 'none';

    files.forEach(f => {
      const item = document.createElement('div');
      item.className = 'file-item' + (f.id === activeFileId ? ' active' : '');

      const thumb = document.createElement('img');
      thumb.className = 'thumb';
      thumb.src = f.objectUrl;

      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.innerHTML = `<div class="fname">${escapeHtml(f.name)}</div><div class="fsize">${formatSize(f.size)}</div>`;

      const del = document.createElement('button');
      del.className = 'del';
      del.innerHTML = '&times;';
      del.title = 'Remove';
      del.onclick = (e) => { e.stopPropagation(); removeFile(f.id); };

      item.onclick = () => selectFile(f.id);
      item.appendChild(thumb);
      item.appendChild(meta);
      item.appendChild(del);
      fileListEl.appendChild(item);
    });
  }

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function addFiles(fileBlobs) {
    let firstNewId = null;
    Array.from(fileBlobs).forEach(blob => {
      if (!blob.type.startsWith('image/')) return;
      const id = 'f_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      const objectUrl = URL.createObjectURL(blob);
      files.push({
        id,
        name: blob.name || 'pasted-image.png',
        size: blob.size,
        file: blob,
        objectUrl,
      });
      if (firstNewId === null) firstNewId = id;
    });
    renderFileList();
    if (firstNewId) selectFile(firstNewId);
  }

  function removeFile(id) {
    const f = files.find(x => x.id === id);
    if (f) URL.revokeObjectURL(f.objectUrl);
    files = files.filter(x => x.id !== id);
    if (activeFileId === id) {
      activeFileId = null;
      resetWorkspace();
      if (files.length > 0) selectFile(files[0].id);
    }
    renderFileList();
  }

  function resetWorkspace() {
    originalBoard.innerHTML = '<div class="placeholder">Upload an image to see it here</div>';
    blurredBoard.innerHTML = '<div class="placeholder">Choose a method to generate a preview</div>';
    currentMethod = null;
    currentBlurredBase64 = null;
    currentBlurredHash = null;
    btnGaussian.classList.remove('selected');
    btnPixelate.classList.remove('selected');
    btnGaussian.disabled = true;
    btnPixelate.disabled = true;
    intensitySlider.disabled = true;
    btnCopy.disabled = true;
    btnSave.disabled = true;
  }

  function selectFile(id) {
    activeFileId = id;
    renderFileList();
    const f = activeFile();
    if (!f) return;

    originalBoard.innerHTML = `<img src="${f.objectUrl}" alt="Original" />`;
    blurredBoard.innerHTML = '<div class="placeholder">Choose a method to generate a preview</div>';
    currentMethod = null;
    currentBlurredBase64 = null;
    currentBlurredHash = null;
    btnGaussian.classList.remove('selected');
    btnPixelate.classList.remove('selected');
    btnGaussian.disabled = false;
    btnPixelate.disabled = false;
    intensitySlider.disabled = true;
    btnCopy.disabled = true;
    btnSave.disabled = true;
  }

  // ---- Upload interactions -------------------------------------------------
  browseBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => addFiles(e.target.files));

  dropzone.addEventListener('click', (e) => {
    if (e.target === browseBtn) return;
    fileInput.click();
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    addFiles(e.dataTransfer.files);
  });

  // Paste support (Ctrl+V) anywhere on the page
  document.addEventListener('paste', (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    const imageBlobs = [];
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        const blob = item.getAsFile();
        if (blob) imageBlobs.push(blob);
      }
    }
    if (imageBlobs.length > 0) addFiles(imageBlobs);
  });

  // ---- Blur processing (calls /api/process) -------------------------------
  async function runBlur() {
    const f = activeFile();
    if (!f || !currentMethod) return;

    blurredBoard.innerHTML = '<div class="placeholder">Processing…</div>';

    const form = new FormData();
    form.append('file', f.file, f.name);
    form.append('method', currentMethod);
    form.append('intensity', intensitySlider.value);

    try {
      const res = await fetch('/api/process', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await safeJson(res);
        throw new Error(err?.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      currentBlurredBase64 = data.blurred_image_base64;
      currentBlurredHash = data.blurred_hash;
      blurredBoard.innerHTML = `<img src="data:image/png;base64,${currentBlurredBase64}" alt="Blurred preview" />`;
      btnCopy.disabled = false;
      btnSave.disabled = false;
    } catch (err) {
      blurredBoard.innerHTML = '<div class="placeholder">Could not generate preview</div>';
      setStatus(err.message || 'Failed to process image', 'error');
    }
  }

  async function safeJson(res) {
    try { return await res.json(); } catch { return null; }
  }

  function selectMethod(method) {
    if (!activeFile()) return;
    currentMethod = method;
    btnGaussian.classList.toggle('selected', method === 'gaussian');
    btnPixelate.classList.toggle('selected', method === 'pixelate');
    intensitySlider.disabled = false;
    runBlur();
  }

  btnGaussian.addEventListener('click', () => selectMethod('gaussian'));
  btnPixelate.addEventListener('click', () => selectMethod('pixelate'));

  intensitySlider.addEventListener('input', () => {
    intensityLevel.textContent = 'Level ' + intensitySlider.value;
    if (!currentMethod) return;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runBlur, 220); // debounce live-updates while dragging
  });

  // ---- Store (Save / Copy both persist to the database) -------------------
  async function storeCurrentPair() {
    const f = activeFile();
    if (!f || !currentBlurredBase64 || !currentBlurredHash || !currentMethod) return null;

    const form = new FormData();
    form.append('original_file', f.file, f.name);
    form.append('blurred_image_base64', currentBlurredBase64);
    form.append('blurred_hash', currentBlurredHash);
    form.append('method', currentMethod);

    const res = await fetch('/api/store', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await safeJson(res);
      throw new Error(err?.detail || `Server returned ${res.status}`);
    }
    return res.json();
  }

  btnSave.addEventListener('click', async () => {
    if (!currentBlurredBase64) return;
    btnSave.disabled = true;
    try {
      const result = await storeCurrentPair();
      // Trigger a real file download of the blurred image
      const link = document.createElement('a');
      link.href = `data:image/png;base64,${currentBlurredBase64}`;
      link.download = 'blurred_' + (activeFile()?.name?.replace(/\.[^.]+$/, '') || 'image') + '.png';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      setStatus(result.status === 'already_stored' ? 'Already stored in database' : 'Saved & stored in database', 'success');
    } catch (err) {
      setStatus(err.message || 'Failed to save', 'error');
    } finally {
      btnSave.disabled = false;
    }
  });

  btnCopy.addEventListener('click', async () => {
    if (!currentBlurredBase64) return;
    btnCopy.disabled = true;
    try {
      const result = await storeCurrentPair();

      // Copy the blurred image to the clipboard as PNG
      const byteChars = atob(currentBlurredBase64);
      const byteNumbers = new Array(byteChars.length);
      for (let i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
      const blob = new Blob([new Uint8Array(byteNumbers)], { type: 'image/png' });

      if (navigator.clipboard && window.ClipboardItem) {
        await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': blob })]);
      }

      setStatus(result.status === 'already_stored' ? 'Already stored in database' : 'Copied & stored in database', 'success');
    } catch (err) {
      setStatus(err.message || 'Failed to copy', 'error');
    } finally {
      btnCopy.disabled = false;
    }
  });
})();