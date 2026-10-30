// --- Bildirim alanı ----------------------------------------------------------

// notify('metin', { error, details: [...], action: { label, onclick } })
function notify(text, { error = false, details = null, action = null } = {}) {
  const box = $('notice');
  box.classList.toggle('error', error);
  box.replaceChildren(el('div', { class: 'notice-row' },
    el('span', { class: 'notice-text' }, text),
    action && el('button', { type: 'button', class: 'small-btn', onclick: action.onclick }, action.label),
    el('button', { type: 'button', class: 'small-btn', 'aria-label': 'Bildirimi kapat', onclick: clearNotice }, '✕'),
  ));
  if (details && details.length) {
    box.append(el('details', {}, el('summary', {}, 'Ayrıntılar'), el('ul', {}, details.map(d => el('li', {}, d)))));
  }
  box.scrollIntoView({ block: 'nearest' });
}

function clearNotice() {
  $('notice').classList.remove('error');
  $('notice').replaceChildren();
}

function notifyError(prefix, err) {
  notify(`${prefix}: ${err.message}`, { error: true });
}

// --- Onay penceresi ----------------------------------------------------------

// Tarayıcının confirm()'ü uzun listeleri taşırır; burada ilk birkaç gönderen görünür, gerisi katlanır.
// Odak "Vazgeç"te başlar: Enter'a yanlışlıkla basmak işlemi başlatmasın.
function confirmDialog({ title, lines = [], items = [], warning = '', confirmLabel }) {
  const dialog = $('confirmDialog');
  $('confirmTitle').textContent = title;
  const rest = items.slice(DIALOG_LIST_LIMIT);
  // replaceChildren null'ı "null" metni olarak ekler; boş parçaları ayıkla.
  $('confirmContent').replaceChildren(...[
    ...lines.map(line => el('p', {}, line)),
    items.length ? el('ul', {}, items.slice(0, DIALOG_LIST_LIMIT).map(item => el('li', {}, item))) : null,
    rest.length ? el('details', {}, el('summary', {}, `ve ${rest.length} gönderen daha`),
                     el('ul', {}, rest.map(item => el('li', {}, item)))) : null,
    warning ? el('p', { class: 'dialog-warning' }, warning) : null,
  ].filter(Boolean));
  $('confirmOk').textContent = confirmLabel;
  dialog.returnValue = '';
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
    dialog.showModal();
    $('confirmCancel').focus();
  });
}

