// uiscript.js

// Sofort globale Drag-Verhinderung registrieren (wird auch noch einmal nach DOMContentLoaded geprüft)
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => e.preventDefault());

document.addEventListener('DOMContentLoaded', () => {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const selectedFile = document.getElementById('selectedFile');
  const errorMsg = document.getElementById('errorMsg');
  const form = document.getElementById('uploadForm');
  const submitBtn = document.getElementById('submitBtn');
  const progressWrap = document.querySelector('.progress');
  const progressBar = document.getElementById('progressBar');

  if (!dropzone || !fileInput || !form) {
    console.error('Essenzielle Elemente fehlen: dropzone/fileInput/form');
    return;
  }

  const ALLOWED = ['video/mp4', 'video/quicktime', 'video/x-matroska'];

  function describeFile(file) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    return `${file.name} — ${mb} MB`;
  }

  function clearError() {
    if (!errorMsg) return;
    errorMsg.style.display = 'none';
    errorMsg.textContent = '';
  }

  function showError(text) {
    if (!errorMsg) return;
    errorMsg.textContent = text;
    errorMsg.style.display = 'block';
  }

  function validate(file) {
    if (!file) return false;
    if (!ALLOWED.includes(file.type)) {
      showError('Ungültiges Format. Erlaubt sind MP4, MOV, MKV.');
      return false;
    }
    clearError();
    return true;
  }

  function setFile(file) {
    if (!validate(file)) {
      try { fileInput.value = ''; } catch (e) {}
      if (selectedFile) selectedFile.textContent = '';
      return;
    }
    if (selectedFile) selectedFile.textContent = describeFile(file);
  }

  // Dropzone: visuelles Feedback + verhindern, dass der Browser die Datei öffnet
  ['dragenter','dragover'].forEach(ev => {
    dropzone.addEventListener(ev, e => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave','drop'].forEach(ev => {
    dropzone.addEventListener(ev, e => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    e.stopPropagation();
    const dt = e.dataTransfer;
    const file = dt?.files?.[0];
    if (file) {
      // Manche Browser erlauben direkte Zuweisung; wenn nicht, bleibt nur Anzeige/Upload per FormData
      try {
        fileInput.files = dt.files;
      } catch (err) {
        // fallback: keine direkte Zuweisung möglich, aber wir zeigen Datei an
      }
      setFile(file);
    }
  });

  // Erlaube Klick auf Dropzone, um Input zu öffnen
  dropzone.addEventListener('click', () => fileInput.click());

  // Keyboard focus
  dropzone.addEventListener('focus', () => dropzone.classList.add('focus'));
  dropzone.addEventListener('blur',  () => dropzone.classList.remove('focus'));

  fileInput.addEventListener('change', e => setFile(e.target.files?.[0]));

  form.addEventListener('submit', async (e) => {
    const file = fileInput.files?.[0];
    if (!validate(file)) {
      e.preventDefault();
      return;
    }

    // Wenn AJAX-Upload gewünscht, Standard-Submit durch fetch/XHR ersetzen
    submitBtn.disabled = true;
    submitBtn.textContent = 'Wird hochgeladen…';
    if (progressWrap) progressWrap.hidden = false;

    // Simulierte Fortschrittsanzeige
    let val = 0;
    if (progressBar) progressBar.value = 0;
    const timer = setInterval(() => {
      val = Math.min(100, val + 3 + Math.random() * 5);
      if (progressBar) progressBar.value = val;
      if (val >= 100) clearInterval(timer);
    }, 120);
  });
});
